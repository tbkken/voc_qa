#!/usr/bin/env python3
"""
VoC Insight Report Generator

调用 VoC 服务 /api/ask 逐条执行数据需求，
根据 chart_hint 生成 Mermaid 图表或 MD 表格，
最后调用 LLM 生成整体洞察总结，输出完整 Markdown 报告。

用法：
    python generate_report.py \
        --background "分析上月续航问题" \
        --items '["负向声量TOP10", "月度趋势", "各渠道负向占比"]' \
        [--api-url http://localhost:8000] \
        [--output report.md] \
        [--no-mermaid]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import httpx
except ImportError:
    print("缺少依赖，请先运行: pip install httpx", file=sys.stderr)
    sys.exit(1)


# ── 图表渲染 ─────────────────────────────────────────────

def _trunc(text: str, max_len: int) -> str:
    s = str(text).replace('"', '').replace('\n', ' ').strip()
    return s if len(s) <= max_len else s[:max_len - 1] + "…"


def _to_float(val) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def render_md_table(columns: list, rows: list, max_rows: int = 30) -> str:
    if not columns or not rows:
        return "_（无数据）_"
    display = rows[:max_rows]
    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep    = "| " + " | ".join("---" for _ in columns) + " |"
    body   = "\n".join(
        "| " + " | ".join("" if v is None else str(v) for v in row) + " |"
        for row in display
    )
    result = f"{header}\n{sep}\n{body}"
    if len(rows) > max_rows:
        result += f"\n\n_（仅展示前 {max_rows} 行，共 {len(rows)} 行）_"
    return result


def render_metric(columns: list, rows: list) -> str:
    col = columns[0] if columns else "结果"
    val = rows[0][0] if rows and rows[0] else "—"
    return f"**{col}**：`{val}`"


def render_mermaid_pie(title: str, columns: list, rows: list) -> str:
    slices = []
    for row in rows[:10]:
        label = _trunc(row[0], 12)
        v = _to_float(row[-1])
        if v is not None:
            slices.append(f'  "{label}" : {v}')
    if not slices:
        return render_md_table(columns, rows)
    return "\n".join([
        "```mermaid",
        f'pie title {_trunc(title, 20)}',
        *slices,
        "```",
    ])


def render_mermaid_bar(title: str, columns: list, rows: list) -> str:
    display = rows[:12]
    labels = [f'"{_trunc(r[0], 8)}"' for r in display]
    values = [_to_float(r[-1]) for r in display]
    if any(v is None for v in values):
        return render_md_table(columns, rows)
    max_val = max(values) or 1
    y_label = _trunc(columns[-1], 10) if len(columns) > 1 else "数量"
    return "\n".join([
        "```mermaid",
        "xychart-beta",
        f'  title "{_trunc(title, 20)}"',
        f"  x-axis [{', '.join(labels)}]",
        f'  y-axis "{y_label}" 0 --> {max_val}',
        f"  bar [{', '.join(str(v) for v in values)}]",
        "```",
    ])


def render_mermaid_line(title: str, columns: list, rows: list) -> str:
    display = rows[:24]
    labels = [f'"{_trunc(r[0], 8)}"' for r in display]
    values = [_to_float(r[-1]) for r in display]
    if any(v is None for v in values):
        return render_md_table(columns, rows)
    max_val = max(values) or 1
    y_label = _trunc(columns[-1], 10) if len(columns) > 1 else "数量"
    return "\n".join([
        "```mermaid",
        "xychart-beta",
        f'  title "{_trunc(title, 20)}"',
        f"  x-axis [{', '.join(labels)}]",
        f'  y-axis "{y_label}" 0 --> {max_val}',
        f"  line [{', '.join(str(v) for v in values)}]",
        "```",
    ])


def render_chart(item_title: str, result: dict, use_mermaid: bool) -> str:
    hint    = result.get("chart_hint", "table")
    columns = result["data"].get("columns", [])
    rows    = result["data"].get("rows", [])

    if hint == "metric":
        return render_metric(columns, rows)
    if not use_mermaid or hint in ("table", "none"):
        return render_md_table(columns, rows)
    if hint == "pie":
        return render_mermaid_pie(item_title, columns, rows)
    if hint == "bar":
        return render_mermaid_bar(item_title, columns, rows)
    if hint == "line":
        return render_mermaid_line(item_title, columns, rows)
    return render_md_table(columns, rows)


# ── VoC API 调用 ──────────────────────────────────────────

def call_ask(api_url: str, question: str, timeout: int = 120) -> dict:
    url = f"{api_url.rstrip('/')}/api/ask"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json={"question": question})
        resp.raise_for_status()
        return resp.json()


# ── LLM 洞察总结 ──────────────────────────────────────────

def call_llm_summary(background: str, items: list[str], narrations: list[str]) -> str:
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    api_key  = os.environ.get("LLM_API_KEY", "")
    model    = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not base_url or not api_key:
        return "_（未配置 LLM 环境变量，跳过洞察总结）_"

    data_block = "\n\n".join(
        f"【需求 {i+1}】{item}\n结论：{narration}"
        for i, (item, narration) in enumerate(zip(items, narrations))
    )
    background_line = f"分析背景：{background}\n\n" if background else ""

    prompt = (
        f"{background_line}"
        f"以下是各项数据需求的查询结论：\n\n{data_block}\n\n"
        "请作为专业的 VoC（用户声音）分析师，综合以上数据输出洞察总结（200字以内）：\n"
        "- 指出最核心的问题或趋势\n"
        "- 给出 1-2 条可操作的改进建议\n"
        "- 结论必须严格基于以上数据，不得引入数据中未体现的内容"
    )

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"_（洞察总结生成失败: {e}）_"


# ── 报告组装 ──────────────────────────────────────────────

def generate_report(api_url: str, background: str, items: list[str],
                    use_mermaid: bool = True) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts: list[str] = []

    # 报告头
    parts.append("# VoC 洞察分析报告")
    parts.append(f"_生成时间：{now}_\n")
    if background:
        parts.append(f"**分析背景**：{background}\n")
    parts.append("---")

    successful_items: list[str] = []
    successful_narrations: list[str] = []

    for i, item in enumerate(items, 1):
        question = f"{background}，{item}" if background else item
        parts.append(f"\n## {i}. {item}\n")

        try:
            result = call_ask(api_url, question)
        except Exception as e:
            parts.append(f"> ⚠️ 接口调用失败：{e}\n")
            continue

        if result.get("error"):
            parts.append(f"> ⚠️ {result.get('answer', '查询失败')}\n")
            raw_sql = result.get("raw_sql", "")
            if raw_sql:
                parts.append(f"<details><summary>SQL（未通过校验）</summary>\n\n```sql\n{raw_sql}\n```\n\n</details>\n")
            continue

        # 图表 / 表格
        parts.append(render_chart(item, result, use_mermaid))
        parts.append("")

        # 自然语言解读
        answer = result.get("answer", "")
        if answer:
            parts.append(f"> {answer}\n")

        # SQL（折叠）
        sql = result.get("sql", "")
        if sql:
            parts.append(f"<details><summary>SQL</summary>\n\n```sql\n{sql}\n```\n\n</details>\n")

        successful_items.append(item)
        successful_narrations.append(answer)

    # 洞察总结
    parts.append("\n---\n\n## 核心洞察总结\n")
    if successful_items:
        parts.append(call_llm_summary(background, successful_items, successful_narrations))
    else:
        parts.append("_所有数据需求均查询失败，无法生成洞察总结。_")

    return "\n".join(parts)


# ── 入口 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VoC 洞察报告生成器")
    parser.add_argument("--api-url",
                        default=os.environ.get("VOC_API_URL", "http://localhost:8000"),
                        help="VoC 服务地址")
    parser.add_argument("--background", default="", help="分析背景（可选）")
    parser.add_argument("--items", required=True,
                        help='数据需求列表，JSON 数组，如 \'["需求1","需求2"]\'')
    parser.add_argument("--output", default="", help="输出文件路径（默认 stdout）")
    parser.add_argument("--no-mermaid", action="store_true",
                        help="禁用 Mermaid，所有图表降级为 MD 表格")
    args = parser.parse_args()

    try:
        items = json.loads(args.items)
        if not isinstance(items, list) or not items:
            raise ValueError("items 必须是非空 JSON 数组")
    except Exception as e:
        print(f"参数错误 --items: {e}", file=sys.stderr)
        sys.exit(1)

    report = generate_report(
        api_url=args.api_url,
        background=args.background,
        items=items,
        use_mermaid=not args.no_mermaid,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存至: {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
