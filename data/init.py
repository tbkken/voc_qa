"""数据初始化脚本:扫描真实 CSV,派生出所有依赖数据的配置项,写入 schema_config.json。

运行:
    python data/init.py data/sample_voc.csv
    python data/init.py /path/to/real.csv --out data/schema_config.json

生成的 schema_config.json 包含:
  - table_name / row_count / date_range
  - fields[]:带业务语义说明
  - enums{}:枚举值(含频率 Top-K)
  - few_shots[]:根据真实数据反算出的"问题 → SQL"示例
  - stats:分布特征(给 LLM 当 hint)

之后启动 API 服务时,LLM prompt 和 schema 都从这个配置文件读取,
做到**代码里不再硬编码任何依赖数据的信息**。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 允许直接 python data/init.py 运行
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb


# ============ 字段语义词典 ============
# 这个是工程师对上游字段的语义理解,不属于"运行时派生",因此允许在这里集中维护
# 如果上游加字段,只要在这里加一行描述就能被 LLM 理解
FIELD_SEMANTICS: dict[str, dict[str, str]] = {
    "pt_d":                     {"desc": "数据日期(分区键)", "format": "YYYYMMDD 字符串,如 '20260401'"},
    "source_sound_id":          {"desc": "声量唯一标识", "format": "字符串 ID"},
    "comment_time":              {"desc": "评论产生时间", "format": "YYYY-MM-DD HH:MM:SS"},
    "business_category_name":   {"desc": "业务分类名称(上游业务视角)", "format": "中文字符串"},
    "content":                  {"desc": "用户评论原文", "format": "中文长文本,可能包含地址/诉求"},
    "is_show":                  {"desc": "是否对外展示", "format": "0 或 1"},
    "data_channel":             {"desc": "数据来源渠道", "format": "枚举,见 enums.data_channel"},
    "emotion":                  {"desc": "情感极性(重要过滤字段)", "format": "枚举,如 '负向声量'/'正向声量'/'中性声量'"},
    "first_category":           {"desc": "一级分类(业务大类)", "format": "枚举,如 '客户服务'/'产品质量'"},
    "fifth_category":           {"desc": "五级分类(最细粒度问题点)", "format": "枚举,如 '客服推脱责任'/'手机频繁死机'"},
    "keywords_emotion":         {"desc": "关键词-情感标签", "format": "如 '客服推脱-负向观点'"},
}


def scan_csv_with_duckdb(csv_path: Path) -> duckdb.DuckDBPyConnection:
    """把 CSV 加载到内存 DuckDB,便于后续统一用 SQL 做统计。"""
    con = duckdb.connect(":memory:")
    con.execute(f"""
        CREATE TABLE fact_voc AS
        SELECT * FROM read_csv_auto('{csv_path}', header=true,
                                    all_varchar=true, ignore_errors=true)
    """)
    return con


def derive_row_count(con) -> int:
    return con.execute("SELECT COUNT(*) FROM fact_voc").fetchone()[0]


def derive_date_range(con) -> dict:
    row = con.execute("SELECT MIN(pt_d), MAX(pt_d) FROM fact_voc").fetchone()
    min_pt, max_pt = row[0], row[1]

    # 同时派生出"本月/上月"等便于 LLM 引用的语义月份
    cur_month = max_pt[:6] if max_pt else ""
    # 上月 = cur_month 的前一个月
    if cur_month:
        y, m = int(cur_month[:4]), int(cur_month[4:])
        pm_y, pm_m = (y - 1, 12) if m == 1 else (y, m - 1)
        prev_month = f"{pm_y:04d}{pm_m:02d}"
    else:
        prev_month = ""

    return {
        "min": min_pt,
        "max": max_pt,
        "current_month": cur_month,
        "previous_month": prev_month,
        "month_count": con.execute(
            "SELECT COUNT(DISTINCT SUBSTR(pt_d,1,6)) FROM fact_voc"
        ).fetchone()[0],
    }


def derive_fields(con) -> list[dict]:
    """结合 DESCRIBE 结果和 FIELD_SEMANTICS 字典,产出字段清单。"""
    cols = con.execute("DESCRIBE fact_voc").fetchall()
    out = []
    for col in cols:
        name = col[0]
        sem = FIELD_SEMANTICS.get(name, {"desc": "(未标注)", "format": ""})
        out.append({
            "name": name,
            "type": col[1],
            "desc": sem["desc"],
            "format": sem["format"],
        })
    return out


def derive_enums(con, fields: list[dict], top_k: int = 30) -> dict[str, dict]:
    """对低基数的维度字段派生枚举值(按频率 TopK),带出现次数。"""
    enum_fields = ["emotion", "data_channel", "business_category_name",
                   "first_category", "fifth_category"]
    enums = {}
    for f in enum_fields:
        if f not in [x["name"] for x in fields]:
            continue
        rows = con.execute(f"""
            SELECT {f} AS v, COUNT(*) AS cnt
            FROM fact_voc
            WHERE {f} IS NOT NULL AND {f} <> ''
            GROUP BY {f}
            ORDER BY cnt DESC
            LIMIT {top_k}
        """).fetchall()
        enums[f] = {
            "distinct_count": con.execute(
                f"SELECT COUNT(DISTINCT {f}) FROM fact_voc"
            ).fetchone()[0],
            "top_values": [{"value": r[0], "count": r[1]} for r in rows],
        }
    return enums


def derive_stats(con) -> dict:
    """一些对 LLM 有帮助的分布特征。"""
    # 情感占比
    emotion_dist = con.execute("""
        SELECT emotion, COUNT(*) AS cnt,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS ratio
        FROM fact_voc GROUP BY emotion ORDER BY cnt DESC
    """).fetchall()
    # 各渠道总量
    channel_total = con.execute("""
        SELECT data_channel, COUNT(*) AS cnt
        FROM fact_voc GROUP BY data_channel ORDER BY cnt DESC
    """).fetchall()
    # 月度声量(给 LLM 看体量级别)
    month_total = con.execute("""
        SELECT SUBSTR(pt_d,1,6) AS m, COUNT(*) AS cnt
        FROM fact_voc GROUP BY m ORDER BY m
    """).fetchall()
    return {
        "emotion_dist": [{"emotion": r[0], "count": r[1], "ratio": r[2]} for r in emotion_dist],
        "channel_total": [{"channel": r[0], "count": r[1]} for r in channel_total],
        "month_total": [{"month": r[0], "count": r[1]} for r in month_total],
    }


def derive_few_shots(con, enums: dict, date_range: dict) -> list[dict]:
    """
    反算 Few-shot 示例:根据真实数据里出现的枚举值,构造 7-8 个**贴合真实数据**的
    "问题 → SQL"示例。这样 LLM 看到的提示里的分类名、渠道名、情感标签都是真实存在的,
    不会出现幻觉(hallucinate 不存在的枚举值)。
    """
    cur_month = date_range.get("current_month", "")
    prev_month = date_range.get("previous_month", "")

    # 挑几个真实存在的 Top 分类和渠道
    top_fifth = [v["value"] for v in enums.get("fifth_category", {}).get("top_values", [])[:5]]
    top_channel = [v["value"] for v in enums.get("data_channel", {}).get("top_values", [])[:3]]
    emotions = [v["value"] for v in enums.get("emotion", {}).get("top_values", [])]
    negative_emotion = next((e for e in emotions if "负向" in e or "negative" in e.lower()), "负向声量")

    few_shots = []

    # 1. 基础 COUNT
    few_shots.append({
        "question": "当前数据里一共有多少条记录?",
        "sql": "SELECT COUNT(*) AS total FROM fact_voc;",
    })

    # 2. TOP 负向榜(最常见的提问)
    few_shots.append({
        "question": "负向声量最多的前 10 个具体问题是什么?",
        "sql": f"""SELECT fifth_category, COUNT(*) AS cnt
FROM fact_voc
WHERE emotion = '{negative_emotion}'
GROUP BY fifth_category
ORDER BY cnt DESC
LIMIT 10;""",
    })

    # 3. 月度趋势
    few_shots.append({
        "question": "最近几个月的声量趋势如何?",
        "sql": f"""SELECT SUBSTR(pt_d,1,6) AS month,
       COUNT(*) AS total,
       SUM(CASE WHEN emotion = '{negative_emotion}' THEN 1 ELSE 0 END) AS negative
FROM fact_voc
GROUP BY month
ORDER BY month;""",
    })

    # 4. 渠道对比(用真实渠道值)
    if top_channel:
        few_shots.append({
            "question": "各个渠道的负向占比是多少?",
            "sql": f"""SELECT data_channel,
       COUNT(*) AS total,
       SUM(CASE WHEN emotion = '{negative_emotion}' THEN 1 ELSE 0 END) AS negative,
       ROUND(100.0 * SUM(CASE WHEN emotion = '{negative_emotion}' THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_ratio
FROM fact_voc
GROUP BY data_channel
ORDER BY total DESC;""",
        })

    # 5. 本月 vs 上月 环比(用真实月份值)
    if cur_month and prev_month:
        few_shots.append({
            "question": "本月和上月相比,哪类问题的负向投诉增长最多?",
            "sql": f"""WITH cur AS (
  SELECT fifth_category, COUNT(*) AS cur_cnt
  FROM fact_voc
  WHERE SUBSTR(pt_d,1,6) = '{cur_month}' AND emotion = '{negative_emotion}'
  GROUP BY fifth_category
), pre AS (
  SELECT fifth_category, COUNT(*) AS pre_cnt
  FROM fact_voc
  WHERE SUBSTR(pt_d,1,6) = '{prev_month}' AND emotion = '{negative_emotion}'
  GROUP BY fifth_category
)
SELECT c.fifth_category,
       c.cur_cnt,
       COALESCE(p.pre_cnt, 0) AS pre_cnt,
       (c.cur_cnt - COALESCE(p.pre_cnt, 0)) AS delta
FROM cur c LEFT JOIN pre p USING(fifth_category)
ORDER BY delta DESC
LIMIT 10;""",
        })

    # 6. 某个真实渠道内的负向 TOP(用第一个真实渠道做示例)
    if top_channel and cur_month:
        ch = top_channel[0]
        few_shots.append({
            "question": f"{ch}渠道本月的负向问题 TOP 有哪些?",
            "sql": f"""SELECT fifth_category, COUNT(*) AS cnt
FROM fact_voc
WHERE SUBSTR(pt_d,1,6) = '{cur_month}'
  AND data_channel = '{ch}'
  AND emotion = '{negative_emotion}'
GROUP BY fifth_category
ORDER BY cnt DESC
LIMIT 10;""",
        })

    # 7. 特定问题点的时间分布(用真实 Top1 问题点)
    if top_fifth:
        problem = top_fifth[0]
        few_shots.append({
            "question": f"『{problem}』这个问题最近几个月的变化趋势?",
            "sql": f"""SELECT SUBSTR(pt_d,1,6) AS month, COUNT(*) AS cnt
FROM fact_voc
WHERE fifth_category = '{problem}'
  AND emotion = '{negative_emotion}'
GROUP BY month
ORDER BY month;""",
        })

    # 8. 情感分布饼图
    few_shots.append({
        "question": "整体情感分布是怎样的?",
        "sql": """SELECT emotion,
       COUNT(*) AS cnt,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS ratio
FROM fact_voc
GROUP BY emotion
ORDER BY cnt DESC;""",
    })

    # 9. 原声样例(LIMIT 而非聚合,演示"查明细"语义)
    if top_fifth:
        problem = top_fifth[0]
        few_shots.append({
            "question": f"随机看几条『{problem}』的原声评论",
            "sql": f"""SELECT comment_time, data_channel, content
FROM fact_voc
WHERE fifth_category = '{problem}'
ORDER BY comment_time DESC
LIMIT 5;""",
        })

    return few_shots


# ============ 主流程 ============
def init(csv_path: Path, out_path: Path) -> dict:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 不存在: {csv_path}")

    print(f"📄 扫描 CSV: {csv_path}")
    print(f"   文件大小: {csv_path.stat().st_size / 1024 / 1024:.1f} MB")

    con = scan_csv_with_duckdb(csv_path)

    print("🔍 派生基本信息...")
    row_count = derive_row_count(con)
    date_range = derive_date_range(con)
    print(f"   行数: {row_count:,}")
    print(f"   时间范围: {date_range['min']} → {date_range['max']}")
    print(f"   跨月数: {date_range['month_count']}")

    print("🔍 派生字段与枚举...")
    fields = derive_fields(con)
    enums = derive_enums(con, fields)
    for k, v in enums.items():
        print(f"   {k}: {v['distinct_count']} 个不重复值 (Top{len(v['top_values'])} 保留)")

    print("📊 派生统计分布...")
    stats = derive_stats(con)

    print("🧠 反算 Few-shot 示例...")
    few_shots = derive_few_shots(con, enums, date_range)
    print(f"   生成 {len(few_shots)} 条贴合真实数据的示例")

    config = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_csv": str(csv_path),
        "table_name": "fact_voc",
        "row_count": row_count,
        "date_range": date_range,
        "fields": fields,
        "enums": enums,
        "stats": stats,
        "few_shots": few_shots,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"\n✅ 配置已生成: {out_path} ({size_kb:.1f} KB)")

    return config


def main():
    parser = argparse.ArgumentParser(description="VoC 数据初始化")
    parser.add_argument("csv", nargs="?", default=str(ROOT / "data" / "sample_voc.csv"),
                        help="源 CSV 路径 (默认 data/sample_voc.csv)")
    parser.add_argument("--out", default=str(ROOT / "data" / "schema_config.json"),
                        help="输出配置文件路径")
    args = parser.parse_args()

    init(Path(args.csv), Path(args.out))


if __name__ == "__main__":
    main()
