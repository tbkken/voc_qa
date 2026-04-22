#!/bin/bash
# 一键启动脚本
export LLM_BASE_URL=https://api.minimaxi.com/v1
export LLM_API_KEY=sk-cp-rysmVDtMt3-7XWQRYNHAJKEtsamGuS5QxsnxBiScIlvYCHpjd8J3SJiPf1-YlTdafWTgo9s27IZ2-UBO2XAtaqIWEKp1MKgcW6ysV381inXP1D5uGBMIu0k
export LLM_MODEL=MiniMax-M2.7
export LLM_MOCK=0

set -e

cd "$(dirname "$0")"

# 0. 检查依赖
python -c "import duckdb, fastapi, uvicorn, httpx" 2>/dev/null || {
  echo "📦 安装依赖..."
  pip install -r requirements.txt
}

# 1. 生成样本数据(如不存在)
if [ ! -f "data/sample_voc.csv" ]; then
  echo "📄 生成样本数据..."
  python data/gen_sample.py
fi

# 2. 初始化 schema 配置(如不存在)
if [ ! -f "data/schema_config.json" ]; then
  echo "🧠 初始化 schema 配置(派生 enums + Few-shot)..."
  python data/init.py
fi

# 3. 检查 LLM 配置
if [ "${LLM_MOCK:-0}" != "1" ] && [ -z "$LLM_BASE_URL" ]; then
  echo ""
  echo "⚠️  未配置真实 LLM,将使用 MOCK 模式启动(仅适合演示)"
  echo "   如需接真实 LLM,请先设置环境变量:"
  echo "     export LLM_BASE_URL=https://your-endpoint/v1"
  echo "     export LLM_API_KEY=sk-xxx"
  echo "     export LLM_MODEL=gpt-4o-mini"
  echo "     export LLM_MOCK=0"
  echo ""
  export LLM_MOCK=1
fi

# 4. 启动服务
echo "🚀 启动 VoC 问答服务 → http://localhost:8000"
echo ""

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
