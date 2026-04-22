# VoC 声量自由问答系统

纯 Python 实现的声量数据自由问答系统。数据只在**内存**中,无 MySQL/Redis 等外部依赖。

## 🎯 核心设计

```
用户提问(自然语言)
      │
      ▼
  真实 LLM 生成 SQL  ←── data/schema_config.json (真实数据派生的 Schema + Few-shot)
      │
      ▼
  SQL Guard 校验     ←── 只允许 SELECT, 白名单表, 强制 LIMIT
      │
      ▼
  DuckDB 内存执行    ←── 启动时 CSV → 内存表
      │
      ▼
  真实 LLM 解读结果  ←── SQL 结果 + 用户问题 → 自然语言
      │
      ▼
  返回 {答案, 图表, 表格, SQL}
```

**为什么选 DuckDB?**
- 纯 Python 包,不是外部服务
- 完整 SQL 兼容
- 几十万行数据聚合在毫秒级
- **迁移友好**:未来数据量大了,把连接换成 MySQL/PostgreSQL,业务代码几乎不改

## 📁 项目结构

```
voc_qa/
├── app/
│   ├── config.py       # schema_config.json 加载器
│   ├── engine.py       # DuckDB 引擎 (CSV 加载 + SQL 执行)
│   ├── sql_guard.py    # SQL 安全校验 (6 重防护)
│   ├── llm.py          # LLM 客户端 (OpenAI 兼容 + Mock 兜底)
│   ├── pipeline.py     # 问答协调器
│   └── main.py         # FastAPI 主入口
├── web/index.html      # 单页聊天式前端
├── data/
│   ├── init.py             # ⭐ 数据初始化脚本:扫描 CSV → 派生配置
│   ├── schema_config.json  # 由 init.py 生成的配置(勿手改)
│   ├── gen_sample.py       # 模拟数据生成器
│   └── sample_voc.csv      # 13.2 万行样本 CSV
├── tests/test_e2e.py   # 端到端测试
├── requirements.txt
├── run.sh              # 一键启动
└── README.md
```

## 🚀 快速开始(三步)

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 初始化数据 (⭐ 必须步骤)

```bash
# 使用样本数据
python data/init.py

# 或指定你的真实 CSV
python data/init.py /path/to/real_voc.csv
```

这一步做了什么:
- 扫描 CSV,派生出**行数、时间范围、字段类型**
- 提取每个枚举字段的**真实值列表**(Top30,按频率)
- **反算** 9 个 Few-shot 示例:问题 → SQL 的对照,枚举值、月份、分类全部用真实数据中存在的值
- 输出到 `data/schema_config.json`

之后 LLM 的 prompt、前端的推荐问题、字段枚举提示,全部从这个文件读 —— 代码里不再有任何硬编码的枚举值。

### 3. 配置 LLM + 启动

```bash
# ① 先配置真实 LLM(任意 OpenAI 兼容 endpoint 均可)
export LLM_MOCK=0
export LLM_BASE_URL=https://your-llm.internal/v1
export LLM_API_KEY=sk-xxx
export LLM_MODEL=gpt-4o-mini                  # 或 qwen2.5-72b-instruct / deepseek-chat 等

# ② 启动服务
./run.sh

# ③ 浏览器访问
# http://localhost:8000
```

### 降级:先跑 Mock 看看效果

如果暂时没有 LLM key,可以先开 Mock 模式看看:

```bash
export LLM_MOCK=1
./run.sh
```

Mock 用关键词匹配生成 SQL,只适合看 UI/流程演示,**真实提问场景必须接真实 LLM**。

## ⚙️ 配置刷新

数据更新时(比如上传新月份的 CSV):

**方式 A - 命令行:**
```bash
python data/init.py data/your_new.csv
# 然后重启服务
```

**方式 B - 通过前端 `/api/upload`:**
上传成功后后端会自动重跑 init,无需重启服务。

## 🔌 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/ask` | POST | 自由问答,`{"question": "..."}` |
| `/api/upload` | POST | 上传新 CSV(multipart),自动刷新配置 |
| `/api/llm_status` | GET | 查询当前 LLM 配置状态 |
| `/api/schema` | GET | 获取完整 schema 配置 |
| `/api/stats` | GET | 数据统计(行数、渠道、分类等) |
| `/api/sample_questions` | GET | 推荐提问(源自 config.few_shots) |
| `/api/health` | GET | 健康检查 |

## 🛡️ 安全设计

1. **SQL 白名单**:只允许 `SELECT` 和 `WITH`
2. **表名白名单**:仅允许查询 `fact_voc`
3. **禁用多语句**:SQL 中不允许 `;` 分割
4. **关键词黑名单**:`INSERT/UPDATE/DELETE/DROP/COPY/ATTACH` 一律禁止
5. **强制 LIMIT**:自动追加 `LIMIT 1000`
6. **注释剥离**:防止通过注释绕过检测

## 🧪 端到端测试

```bash
python tests/test_e2e.py
```

测试覆盖:config 加载、Prompt 构建(含真实枚举注入校验)、Engine 加载、SQL Guard 防御、完整 Pipeline、LLM 配置诊断。

## 🔮 未来升级(无需改业务代码)

当数据量超过内存能力时(几千万行以上):

1. **先:DuckDB 内存 → DuckDB 持久化**
   ```python
   # app/engine.py
   self.con = duckdb.connect("voc.db")   # 改为文件
   ```

2. **再:DuckDB → MySQL/PostgreSQL**
   用 SQLAlchemy 替换 DuckDB 连接,SQL 语法基本兼容标准 ANSI SQL,`data/init.py` 里的派生逻辑可以直接改成从数据库扫描。

所有的 prompt、few-shot、枚举值都由 `data/init.py` 从数据中派生,**代码本身不会因为数据源变化而需要修改**。
