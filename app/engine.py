"""DuckDB 引擎封装:负责加载 CSV 到内存,并执行只读 SQL 查询。

设计要点:
1. 启动时把 CSV 读入内存表 fact_voc,之后所有查询都在内存完成(毫秒级)
2. 支持多文件加载(对应月度增量场景)
3. 只暴露只读执行接口,写入通过 load_csv 方法
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import duckdb


TABLE_NAME = "fact_voc"


class VocEngine:
    """VoC 查询引擎 - 基于 DuckDB 内存实例。"""

    def __init__(self) -> None:
        # ":memory:" 内存模式,进程结束数据消失;生产可换为文件路径
        self.con = duckdb.connect(":memory:")
        self._loaded_files: list[str] = []
        self._ensure_table()

    def _ensure_table(self) -> None:
        """建表。字段类型故意都用 VARCHAR 以最大限度兼容上游 CSV 各种写法。"""
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                pt_d VARCHAR,
                source_sound_id VARCHAR,
                comment_time VARCHAR,
                business_category_name VARCHAR,
                content VARCHAR,
                is_show INTEGER,
                data_channel VARCHAR,
                emotion VARCHAR,
                first_category VARCHAR,
                fifth_category VARCHAR,
                keywords_emotion VARCHAR
            )
        """)

    def load_csv(self, path: str | Path) -> dict[str, Any]:
        """加载一个 CSV 文件到内存表。返回入库统计。"""
        path = str(Path(path).resolve())
        t0 = time.time()

        # DuckDB 的 read_csv_auto 会自动推断编码和分隔符
        before = self.row_count()
        self.con.execute(f"""
            INSERT INTO {TABLE_NAME}
            SELECT pt_d, source_sound_id, comment_time, business_category_name,
                   content, CAST(is_show AS INTEGER), data_channel, emotion,
                   first_category, fifth_category, keywords_emotion
            FROM read_csv_auto('{path}', header=true, all_varchar=true,
                               quote='"', escape='"', ignore_errors=true)
        """)
        after = self.row_count()
        elapsed = time.time() - t0

        self._loaded_files.append(path)
        return {
            "file": path,
            "added_rows": after - before,
            "total_rows": after,
            "elapsed_sec": round(elapsed, 2),
        }

    def row_count(self) -> int:
        return self.con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    def execute(self, sql: str, limit: int = 1000) -> dict[str, Any]:
        """
        执行只读 SQL。调用方已通过 SqlGuard 校验过安全性。
        返回: {columns: [...], rows: [[...]], row_count: N, truncated: bool}
        """
        t0 = time.time()
        result = self.con.execute(sql).fetchmany(limit + 1)
        truncated = len(result) > limit
        if truncated:
            result = result[:limit]
        columns = [d[0] for d in self.con.description] if self.con.description else []

        # 把 Decimal / date 等转换成 JSON 友好类型
        rows = [[_to_json_safe(v) for v in row] for row in result]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    # --------------------- Schema Introspection ---------------------
    def get_schema_info(self) -> dict[str, Any]:
        """返回 schema 概览。

        优先读 data/schema_config.json(由 data/init.py 派生,含业务语义和 few-shot);
        如果配置不存在,fallback 到实时扫库(用于 init 之前的过渡)。
        """
        try:
            from .config import load_schema_config
            cfg = load_schema_config()
            # 配置是静态快照,row_count 改用实时值以反映 upload 等动态变化
            return {
                **cfg,
                "row_count": self.row_count(),
                "source": "schema_config.json",
            }
        except Exception:
            # Fallback:直接扫库
            return self._introspect_live()

    def _introspect_live(self) -> dict[str, Any]:
        """实时扫库生成 schema(fallback 用,缺乏业务语义)。"""
        cols = self.con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()
        fields = [{"name": c[0], "type": c[1], "desc": "", "format": ""} for c in cols]

        enums = {}
        for f in ("emotion", "data_channel", "business_category_name",
                  "first_category", "fifth_category"):
            rows = self.con.execute(
                f"SELECT {f} AS v, COUNT(*) AS cnt FROM {TABLE_NAME} "
                f"WHERE {f} IS NOT NULL AND {f} <> '' "
                f"GROUP BY {f} ORDER BY cnt DESC LIMIT 30"
            ).fetchall()
            enums[f] = {
                "distinct_count": len(rows),
                "top_values": [{"value": r[0], "count": r[1]} for r in rows],
            }

        date_range = self.con.execute(
            f"SELECT MIN(pt_d), MAX(pt_d) FROM {TABLE_NAME}"
        ).fetchone()

        return {
            "table_name": TABLE_NAME,
            "fields": fields,
            "enums": enums,
            "date_range": {"min": date_range[0], "max": date_range[1]},
            "row_count": self.row_count(),
            "few_shots": [],
            "source": "live_introspection",
        }


def _to_json_safe(v: Any) -> Any:
    """把 DuckDB 返回的各种类型转成 JSON 可序列化形式。"""
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    # Decimal / datetime / date 统一转 str
    return str(v)
