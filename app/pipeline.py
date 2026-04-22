"""问答协调器 - 把 LLM、SQL 守卫、DuckDB 引擎串起来。"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any

from .engine import VocEngine
from .llm import LlmClient
from .sql_guard import SqlGuard


@dataclass
class AskResult:
    question: str
    sql: str                          # 经 guard 校验后实际执行的 SQL
    raw_sql: str                      # LLM 原始输出
    answer: str                       # 自然语言回答
    data: dict[str, Any]              # {columns, rows, row_count, truncated}
    chart_hint: str                   # 图表建议: bar/line/table/none
    elapsed_ms: int
    error: str | None = None          # 如有错误

    def to_dict(self) -> dict:
        return asdict(self)


class QaPipeline:
    def __init__(self, engine: VocEngine, llm: LlmClient | None = None,
                 guard: SqlGuard | None = None):
        self.engine = engine
        self.llm = llm or LlmClient()
        self.guard = guard or SqlGuard()

    def ask(self, question: str) -> AskResult:
        t0 = time.time()

        # 1. 生成 SQL (llm 内部自己从 config 加载 schema)
        try:
            raw_sql = self.llm.generate_sql(question)
        except Exception as e:
            return AskResult(question, "", "", f"LLM 调用失败: {e}",
                             _empty_data(), "none",
                             int((time.time() - t0) * 1000), str(e))

        # 2. 校验 SQL
        guard_res = self.guard.check(raw_sql)
        if not guard_res.ok:
            return AskResult(question, "", raw_sql,
                             f"SQL 未通过安全校验: {guard_res.reason}",
                             _empty_data(), "none",
                             int((time.time() - t0) * 1000), guard_res.reason)

        # 3. 执行
        try:
            data = self.engine.execute(guard_res.sql)
        except Exception as e:
            return AskResult(question, guard_res.sql, raw_sql,
                             f"SQL 执行失败: {e}",
                             _empty_data(), "none",
                             int((time.time() - t0) * 1000), str(e))

        # 4. 让 LLM 解读结果
        try:
            answer = self.llm.narrate_result(question, guard_res.sql, data)
        except Exception as e:
            # 解读失败不是致命错误,给个兜底
            answer = f"查询成功,共返回 {data['row_count']} 条结果。(结果解读失败: {e})"

        # 5. 图表建议
        chart_hint = _suggest_chart(guard_res.sql, data)

        return AskResult(
            question=question,
            sql=guard_res.sql,
            raw_sql=raw_sql,
            answer=answer,
            data=data,
            chart_hint=chart_hint,
            elapsed_ms=int((time.time() - t0) * 1000),
        )


class InsightPipeline:
    """串行处理多个数据需求，逐条 yield SSE 事件 dict。"""

    def __init__(self, engine: VocEngine, llm: LlmClient | None = None,
                 guard: SqlGuard | None = None):
        self.engine = engine
        self.llm = llm or LlmClient()
        self.guard = guard or SqlGuard()
        self._qa = QaPipeline(engine, self.llm, self.guard)

    def run(self, background: str, items: list[str]):
        total = len(items)
        results: list[dict | None] = []

        for i, item in enumerate(items):
            yield {"type": "item_start", "index": i, "total": total, "query": item}

            question = f"{background}，{item}" if background else item
            try:
                result = self._qa.ask(question)
                if result.error:
                    yield {"type": "item_error", "index": i, "error": result.answer,
                           "sql": result.raw_sql}
                    results.append(None)
                else:
                    rows = result.data.get("rows", [])
                    chart_type = result.chart_hint if rows else "table"
                    evt: dict[str, Any] = {
                        "type": "item_done",
                        "index": i,
                        "sql": result.sql,
                        "narration": result.answer,
                        "chart_type": chart_type,
                        "columns": result.data.get("columns", []),
                        "rows": rows,
                        "row_count": result.data.get("row_count", 0),
                    }
                    yield evt
                    results.append(evt)
            except Exception as e:
                yield {"type": "item_error", "index": i, "error": f"处理异常: {e}"}
                results.append(None)

        yield {"type": "all_done", "results": results}


def _is_numeric(val) -> bool:
    if val is None:
        return False
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def _suggest_chart(sql: str, data: dict) -> str:
    """根据结果结构推荐图表类型：metric / line / pie / bar / table / none。"""
    rows = data["rows"]
    cols = data["columns"]
    if not rows or not cols:
        return "none"

    # ── 单列 ──────────────────────────────────────────
    if len(cols) == 1:
        # 1行1列数字 → 大数字卡片
        if len(rows) == 1 and _is_numeric(rows[0][0]):
            return "metric"
        # 全部非数字（原声评论、关键词等纯文本）→ 仅表格
        if all(not _is_numeric(r[0]) for r in rows):
            return "table"
        # 单列多行数字 → 表格
        return "table"

    # ── 多列 ──────────────────────────────────────────
    first_col = cols[0].lower()
    # 时间维度 → 折线
    if any(k in first_col for k in ("month", "date", "pt_d", "day", "week", "time")):
        return "line"
    # 2列 + ≤8行 + 末列为数字 → 饼图（整体/局部关系）
    if len(cols) == 2 and len(rows) <= 8 and _is_numeric(rows[0][-1]):
        return "pie"
    # 其他分类数据 ≤30行 → 竖柱状
    if len(rows) <= 30:
        return "bar"
    return "table"


def _empty_data() -> dict:
    return {"columns": [], "rows": [], "row_count": 0, "truncated": False, "elapsed_ms": 0}
