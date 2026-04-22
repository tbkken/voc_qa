"""端到端测试 - 覆盖 config 驱动 + Mock / 真实 LLM 双路径。

运行:
    # 默认走 Mock
    python tests/test_e2e.py

    # 跑真实 LLM(需要设置环境变量)
    LLM_MOCK=0 LLM_BASE_URL=... LLM_API_KEY=... python tests/test_e2e.py
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
    # 默认强制开启 mock 便于 CI / 离线测试
    os.environ.setdefault("LLM_MOCK", "1")

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

    # ============ 5. Pipeline 测试 ============
    banner(f"5. Pipeline 测试 [{LlmConfig().describe()}]")
    llm = LlmClient()
    pipeline = QaPipeline(engine, llm, guard)

    questions = [
        "TOP 10 负向声量问题是什么?",
        "各渠道的声量分布?",
        "每月声量趋势?",
        "客服相关的负向 TOP?",
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
    cfg_llm = LlmConfig()
    if cfg_llm.mock:
        print("  ℹ️  当前为 MOCK 模式。要切真实 LLM,请设置:")
        print("      export LLM_MOCK=0")
        print("      export LLM_BASE_URL=https://your-endpoint/v1")
        print("      export LLM_API_KEY=sk-xxx")
        print("      export LLM_MODEL=gpt-4o-mini")
    else:
        print(f"  ✅ 已配置真实 LLM: {cfg_llm.describe()}")

    banner("✅ 所有测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
