"""端到端测试 - 覆盖 config 驱动、SQL 守卫、Pipeline。

运行:
    python tests/test_e2e.py

Pipeline 测试需要配置真实 LLM（LLM_BASE_URL + LLM_API_KEY），
未配置时自动跳过该节，其余节仍正常执行。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import VocEngine
from app.llm import LlmClient, LlmConfig, build_sql_system_prompt
from app.sql_guard import SqlGuard
from app.pipeline import QaPipeline
from app.config import load_schema_config


def banner(msg):
    print("\n" + "=" * 70)
    print("  " + msg)
    print("=" * 70)


def main():
    # ============ 1. 确保 config 存在 ============
    banner("1. 检查 schema_config.json")
    try:
        cfg = load_schema_config()
        print(f"  ✅ 配置已加载")
        print(f"     行数: {cfg['row_count']:,}")
        print(f"     时间范围: {cfg['date_range']['min']} → {cfg['date_range']['max']}")
        print(f"     字段数: {len(cfg['fields'])}")
        print(f"     枚举字段: {list(cfg['enums'].keys())}")
        print(f"     Few-shot 数: {len(cfg['few_shots'])}")
    except Exception as e:
        print(f"  ❌ 配置未生成: {e}")
        print(f"     请先运行: python data/init.py")
        return 1

    # ============ 2. 验证 Prompt 构建 ============
    banner("2. 验证 LLM Prompt 构建(真实枚举值注入)")
    prompt = build_sql_system_prompt(cfg)
    print(f"  ✅ Prompt 长度: {len(prompt)} 字符")

    # 真实枚举值必须出现在 prompt 里
    emotion_vals = [v["value"] for v in cfg["enums"]["emotion"]["top_values"]]
    for v in emotion_vals:
        assert v in prompt, f"枚举值 {v} 未出现在 prompt 中!"
    print(f"  ✅ emotion 枚举全部注入: {emotion_vals}")

    # Few-shot 必须注入
    fs1 = cfg["few_shots"][0]["question"]
    assert fs1 in prompt, "Few-shot 未注入"
    print(f"  ✅ Few-shot 示例注入正确")

    # 时间范围的真实月份必须出现
    cur_month = cfg["date_range"]["current_month"]
    assert cur_month in prompt, f"当前月 {cur_month} 未出现在 prompt"
    print(f"  ✅ 真实月份 {cur_month} 已注入")

    # ============ 3. Engine + 数据加载 ============
    banner("3. Engine 初始化")
    engine = VocEngine()
    csv = Path(__file__).resolve().parent.parent / "data" / "sample_voc.csv"
    info = engine.load_csv(csv)
    print(f"  ✅ 加载 {info['added_rows']:,} 行, 耗时 {info['elapsed_sec']}s")

    # schema_info 应该来自 config
    schema = engine.get_schema_info()
    print(f"  ✅ schema source: {schema.get('source')}")
    assert schema["source"] == "schema_config.json", f"应优先读 config, 实际={schema.get('source')}"

    # ============ 4. SQL Guard 防御 ============
    banner("4. SQL Guard 防御测试")
    guard = SqlGuard()
    cases = [
        ("SELECT * FROM fact_voc LIMIT 5", True),
        ("DROP TABLE fact_voc", False),
        ("SELECT * FROM fact_voc; DELETE FROM fact_voc", False),
        ("SELECT * FROM users", False),
        ("INSERT INTO fact_voc VALUES (...)", False),
        ("SELECT COUNT(*) FROM fact_voc /* DROP TABLE x */", True),
        ("WITH t AS (SELECT * FROM fact_voc) SELECT * FROM t", True),
    ]
    for sql, expected in cases:
        r = guard.check(sql)
        status = "✅" if r.ok == expected else "❌"
        print(f"  {status} {'允许' if expected else '拦截'}: {sql[:50]}... → ok={r.ok}")

    # ============ 5. Pipeline 测试（需真实 LLM，未配置时跳过） ============
    cfg_llm = LlmConfig()
    banner(f"5. Pipeline 测试 [{cfg_llm.describe()}]")
    if not (cfg_llm.base_url and cfg_llm.api_key):
        print("  ⏭  LLM 未配置，跳过 Pipeline 测试")
        print("     设置 LLM_BASE_URL + LLM_API_KEY 后可运行真实 LLM 测试")
    else:
        llm = LlmClient()
        pipeline = QaPipeline(engine, llm, guard)
        questions = [
            "TOP 10 负向声量问题是什么?",
            "各渠道的声量分布?",
            "每月声量趋势?",
            "情感分布?",
            "总声量是多少?",
        ]
        for q in questions:
            print(f"\n  ❓ {q}")
            r = pipeline.ask(q)
            if r.error:
                print(f"     ❌ {r.error}")
                continue
            first_line = r.sql.strip().split("\n")[0]
            print(f"     📝 {first_line[:80]}...")
            print(f"     💬 {r.answer[:120]}")
            print(f"     📊 {r.data['row_count']} 行 · chart={r.chart_hint} · {r.elapsed_ms}ms")

    # ============ 6. LLM 配置诊断 ============
    banner("6. LLM 配置诊断")
    if cfg_llm.base_url and cfg_llm.api_key:
        print(f"  ✅ 已配置真实 LLM: {cfg_llm.describe()}")
    else:
        print("  ⚠️  LLM 未配置，请设置:")
        print("      export LLM_BASE_URL=https://your-endpoint/v1")
        print("      export LLM_API_KEY=sk-xxx")
        print("      export LLM_MODEL=gpt-4o-mini")

    banner("✅ 所有测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
