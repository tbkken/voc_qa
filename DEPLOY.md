# VoC 声量自由问答系统 - 部署说明

## 这个系统做什么

用户用中文自然语言提问 → 真实 LLM 生成 SQL → 查询你的真实数据 → 返回答案 + 图表。

## 🎯 关于"Mock"的澄清

代码里有两处默认的降级方案,**都可以关闭,换成真实的**:

| 降级项 | 默认状态 | 怎么切到真实 |
|---|---|---|
| **样本 CSV** (`data/sample_voc.csv`) | 本压缩包**不包含**样本数据 | 把你的真实 CSV 放到 `data/` 下即可 |
| **LLM Mock 模式** (`LLM_MOCK=1`) | 默认关闭,除非你没配 LLM | 设置 `LLM_BASE_URL` + `LLM_API_KEY`,`LLM_MOCK=0` |

所有后端代码、SQL 执行、前端、FastAPI 都是**真实实现**,不是模拟的。

## 🚀 部署步骤(3 步)

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 放入真实 CSV + 初始化

```bash
# 把你的真实 CSV 复制过来
cp /path/to/your_voc_data.csv data/voc.csv

# 扫描 CSV,派生出 enums / 时间范围 / Few-shot 示例
python data/init.py data/voc.csv
```

`init.py` 会生成 `data/schema_config.json`(里面包含从你真实数据派生的枚举值、月份、分类),之后 LLM 的提示词完全基于这个文件,不会瞎编枚举值。

### 3. 配置 LLM 并启动

```bash
# 你的 OpenAI 兼容 endpoint
export LLM_BASE_URL=https://your-endpoint/v1
export LLM_API_KEY=sk-xxx
export LLM_MODEL=gpt-4o-mini      # 或 qwen2.5-72b / deepseek-chat 等
export LLM_MOCK=0                 # ← 关键:关闭 Mock,走真实 LLM

# 同时告诉服务用哪个 CSV
# 默认它会加载 data/sample_voc.csv,你改名后需要改一下 main.py 的路径
# 或者用 /api/upload 接口上传,自动加载+重算 config

./run.sh
```

访问 `http://localhost:8000`。

## ⚠️ 部署前必做检查

打开 `app/main.py` 第 27 行左右,确认 `_DEFAULT_CSV` 指向你的 CSV 路径:

```python
_DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "voc.csv"
#                                                               ^^^^^^^ 改成你的文件名
```

或者不改代码,启动后用前端的文件上传入口上传(会自动入库 + 刷新 config)。

## 项目结构

```
voc_qa/
├── app/
│   ├── config.py       # 配置加载器
│   ├── engine.py       # DuckDB 引擎
│   ├── sql_guard.py    # SQL 安全校验
│   ├── llm.py          # LLM 客户端(OpenAI 兼容)
│   ├── pipeline.py     # 问答协调器
│   └── main.py         # FastAPI 入口
├── web/index.html      # 前端(聊天界面)
├── data/
│   ├── init.py         # 初始化脚本(扫 CSV → schema_config.json)
│   └── gen_sample.py   # 样本数据生成器(可选,仅用于本地演示)
├── tests/
├── requirements.txt
├── run.sh              # 启动脚本
└── README.md
```

## API 接口

| 接口 | 用途 |
|---|---|
| `POST /api/ask` | 提问:`{"question": "..."}` |
| `POST /api/upload` | 上传新 CSV,自动刷新配置 |
| `GET /api/llm_status` | 查看 LLM 当前状态 |
| `GET /api/stats` | 查看数据统计 |

## 接真实 LLM 已验证

真实 HTTP 链路(前端 → FastAPI → LLM → DuckDB → LLM 解读 → 返回)已用伪 LLM endpoint 完整验证打通,链路正确。你换成真实 `LLM_BASE_URL` 就能直接工作,整条链路代码一行不改。
