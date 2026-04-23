# Spec: 数据管理与系统接口

**Spec 编号**：SPEC-004
**关联 PRD**：VoC 系统初始设计（数据管理能力）
**版本**：v1.0
**状态**：已确认（补录已上线功能）
**创建日期**：2026-04-23

---

## 背景 & 目标

VoC 系统需要支持数据自助管理：用户上传 CSV → 系统自动加载到 DuckDB → 派生字段语义/枚举值/Few-shot 示例写入 `schema_config.json` → LLM Prompt 自动更新。同时提供系统辅助接口（schema 查看、统计、推荐问题、健康检查、LLM 状态）。

**非目标**（本期明确不做）：
- 多数据集并存（所有数据共用同一张 `fact_voc` 表）
- 数据持久化（DuckDB 内存模式，重启清零）
- 增量删除或数据清洗

---

## 用户故事与验收标准

### US-01：CSV 数据上传与加载（/api/upload）

**作为** VoC 分析师，
**我希望** 通过接口上传新的 VoC CSV 文件，系统自动加载数据并刷新所有配置，
**以便** 无需重启服务即可切换或补充分析数据。

**验收标准**：

- [ ] **AC-01**（正常）：Given 用户 POST `/api/upload` 上传合法 `.csv` 文件，When 上传成功，Then 文件被保存到 `data/uploads/<filename>`；DuckDB 将 CSV 数据追加插入 `fact_voc` 表；自动重新运行 `data/init.py` 用新 CSV 路径生成 `data/schema_config.json`；重新加载内存中的 schema config 缓存；返回 JSON 包含 `file`、`added_rows`、`total_rows`、`elapsed_sec`、`config_refreshed: true`。

- [ ] **AC-02**（正常）：Given CSV 文件包含非 UTF-8 编码或分隔符不规范，When DuckDB 使用 `read_csv_auto`（`all_varchar=true`，`ignore_errors=true`）加载，Then 问题行被跳过，合法行正常入库；不抛出异常，不中断服务。

- [ ] **AC-03**（正常）：Given 服务启动时 `data/sample_voc.csv` 存在，When 模块加载执行，Then 自动调用 `engine.load_csv(sample_voc.csv)`，`fact_voc` 表预填充样本数据；若文件不存在，打印警告但服务正常启动，不崩溃。

- [ ] **AC-04**（异常）：Given 用户上传非 `.csv` 扩展名的文件（如 `.xlsx`、`.json`），When POST `/api/upload`，Then 返回 HTTP 400，`detail = "只支持 .csv 文件"`，不保存文件。

- [ ] **AC-05**（异常）：Given CSV 格式正确但 DuckDB 加载时抛出异常，When `engine.load_csv` 失败，Then 返回 HTTP 500，`detail` 含具体错误信息；文件已保存到 `data/uploads/` 但不影响现有 `fact_voc` 数据。

- [ ] **AC-06**（边界）：Given CSV 加载成功但 `data/init.py` 重新派生配置失败，When `run_init` 抛出异常，Then 返回 JSON 中 `config_refreshed: false`，`config_error: "<错误描述>"`；数据已入库，仅配置刷新失败，不影响查询（使用旧配置）。

---

### US-02：Schema 配置自动派生（data/init.py）

**作为** 系统，
**我希望** 从真实 CSV 数据中自动派生所有依赖数据的配置，
**以便** LLM Prompt 中的枚举值、Few-shot 示例始终与真实数据一致，不出现幻觉。

**验收标准**：

- [ ] **AC-07**（正常）：Given `data/init.py` 被调用（命令行或 upload 触发），When 派生 `fields` 字段，Then 输出包含所有 CSV 列的字段清单，每个字段含 `name`、`type`、`desc`（来自 `FIELD_SEMANTICS` 字典）、`format`（字段格式说明）。

- [ ] **AC-08**（正常）：Given CSV 包含 `emotion`、`data_channel`、`business_category_name`、`first_category`、`fifth_category` 低基数字段，When 派生 `enums`，Then 每个枚举字段输出 `distinct_count` 和 `top_values`（按频率降序，最多 Top-30），每个条目含 `value` 和 `count`。

- [ ] **AC-09**（正常）：Given `enums` 派生完成，When 派生 `few_shots`，Then 生成 7-9 条 Few-shot 示例，SQL 中使用的枚举值（如情感标签、渠道名、分类名）均来自真实数据的 Top 值，不硬编码任何枚举字符串。

- [ ] **AC-10**（正常）：Given CSV 中 `pt_d` 字段含日期值（YYYYMMDD 格式），When 派生 `date_range`，Then 输出 `min`、`max`、`current_month`（最大 pt_d 的前 6 位）、`previous_month`（上一个月的 YYYYMM）、`month_count`（不重复月份数）。

- [ ] **AC-11**（正常）：Given `data/init.py` 被首次运行或重新运行，When 输出 `schema_config.json`，Then 文件包含 `generated_at`（ISO8601 时间戳）、`source_csv`（CSV 路径）、`table_name: "fact_voc"`、`row_count`、`date_range`、`fields`、`enums`、`stats`、`few_shots`；文件编码为 UTF-8。

- [ ] **AC-12**（正常）：Given `load_schema_config()` 被多次调用，When 配置文件未变化，Then 使用 `lru_cache` 缓存，只从磁盘读取一次；调用 `reload_schema_config()` 后缓存清除，下次调用重新读取。

- [ ] **AC-13**（异常）：Given `data/schema_config.json` 不存在，When `load_schema_config()` 被调用，Then 抛出 `ConfigNotFoundError`，错误信息包含文件路径和运行 `python data/init.py` 的提示。

---

### US-03：系统辅助接口

**作为** 前端和运维，
**我希望** 通过接口查看系统状态、数据概览和推荐问题，
**以便** 了解当前数据情况并引导用户使用。

**验收标准**：

- [ ] **AC-14**（正常）：Given GET `/api/schema`，When schema_config.json 已加载，Then 返回 schema 概览 JSON，包含 `table_name`、`fields`（字段列表含语义说明）、`enums`（各维度枚举值及频率）、`date_range`、`row_count`（实时值，非配置快照）、`few_shots`、`source: "schema_config.json"`。

- [ ] **AC-15**（正常）：Given GET `/api/stats`，When 调用，Then 返回 `{ row_count, date_range, channels: [渠道名列表], first_categories: [一级分类列表] }`；`channels` 和 `first_categories` 只含值字符串，不含频率数字。

- [ ] **AC-16**（正常）：Given GET `/api/sample_questions`，When `schema_config.json` 存在且含有效 `few_shots`，Then 返回 `{ questions: [<few_shots 的 question 字段列表>] }`，问题来自真实数据派生的示例，贴合实际枚举值。

- [ ] **AC-17**（边界）：Given GET `/api/sample_questions`，When `schema_config.json` 不存在或 `few_shots` 为空，Then 返回 `{ questions: [6 条通用兜底问题] }`，服务不报错。

- [ ] **AC-18**（正常）：Given GET `/api/health`，When 调用，Then 返回 `{ status: "ok", rows: <当前行数> }`，HTTP 200；无论数据是否为空均返回 200（不做数据校验）。

- [ ] **AC-19**（正常）：Given GET `/api/llm_status`，When 调用，Then 返回 `{ configured: bool, model: "<模型名>", endpoint: "<BASE_URL 或 '(未设置)'>", describe: "<一行描述>" }`；`configured` 为 true 当且仅当 `LLM_BASE_URL` 和 `LLM_API_KEY` 均非空。

- [ ] **AC-20**（边界）：Given GET `/api/schema`，When `schema_config.json` 不存在，Then `engine.get_schema_info()` fallback 到实时扫库（`_introspect_live`），返回字段结构但 `desc` 和 `format` 为空字符串，`source: "live_introspection"`；服务不报 500。

---

## 数据需求

| 字段名 | 类型 | 说明 | 是否必填 | 关联 AC |
|--------|------|------|----------|---------|
| `added_rows` | int | 本次 upload 新增行数 | 是 | AC-01 |
| `total_rows` | int | 表中当前总行数 | 是 | AC-01 |
| `elapsed_sec` | float | CSV 加载耗时（秒） | 是 | AC-01 |
| `config_refreshed` | bool | schema_config 是否已刷新 | 是 | AC-01、AC-06 |
| `config_error` | str | config 刷新失败原因 | 否 | AC-06 |
| `generated_at` | str | schema_config 生成时间（ISO8601） | 是 | AC-11 |
| `few_shots[].question` | str | 推荐问题文本 | 是 | AC-09、AC-16 |
| `few_shots[].sql` | str | 对应 SQL（含真实枚举值） | 是 | AC-09 |
| `enums[field].top_values` | list | `[{value, count}]`，按频率降序 Top-30 | 是 | AC-08 |
| `date_range.current_month` | str | 最近月份 YYYYMM | 是 | AC-10 |
| `date_range.previous_month` | str | 上一个月 YYYYMM | 是 | AC-10 |

---

## 接口需求

- `POST /api/upload` — CSV 上传（关联 US-01：AC-01 ~ AC-06）
  - Request: multipart/form-data，字段名 `file`
  - Response: `{ file, added_rows, total_rows, elapsed_sec, config_refreshed, [config_error] }`
- `GET /api/schema` — Schema 概览（关联 US-03：AC-14、AC-20）
- `GET /api/stats` — 数据统计（关联 US-03：AC-15）
- `GET /api/sample_questions` — 推荐问题（关联 US-03：AC-16、AC-17）
- `GET /api/health` — 健康检查（关联 US-03：AC-18）
- `GET /api/llm_status` — LLM 配置状态（关联 US-03：AC-19）

---

## 非功能需求

| 类型 | 要求 | 关联 AC |
|------|------|---------|
| 安全 | `data/uploads/` 目录不对外暴露静态服务，文件不可直接下载 | AC-01 |
| 幂等性 | 同文件名重复上传会覆盖 `data/uploads/` 中的文件，数据累加入库 | AC-01 |
| 弹性 | CSV 编码/分隔符异常不导致服务崩溃（ignore_errors=true） | AC-02 |
| 性能 | 辅助接口（schema/stats/health）P99 < 200ms | AC-14 ~ AC-18 |

---

## 开放问题（待确认）

| # | 问题 | 影响的 AC |
|---|------|-----------|
| Q1 | 同文件名重复上传时，数据会累加而非替换，可能导致重复统计，是否需要去重逻辑？ | AC-01 |

---

## AC 汇总表

| AC 编号 | 所属故事 | 类型 | 简述 |
|---------|----------|------|------|
| AC-01 | US-01 | 正常 | 上传 CSV → 入库 → 刷新配置 → 返回统计 |
| AC-02 | US-01 | 正常 | 编码/格式异常行跳过，不中断加载 |
| AC-03 | US-01 | 正常 | 启动时自动加载 sample_voc.csv（如存在） |
| AC-04 | US-01 | 异常 | 非 .csv 文件返回 HTTP 400 |
| AC-05 | US-01 | 异常 | DuckDB 加载失败返回 HTTP 500 |
| AC-06 | US-01 | 边界 | init.py 失败时 config_refreshed=false，数据已入库 |
| AC-07 | US-02 | 正常 | fields 含 FIELD_SEMANTICS 字典的 desc/format |
| AC-08 | US-02 | 正常 | 5 个维度字段派生枚举 Top-30（含 count） |
| AC-09 | US-02 | 正常 | few_shots 的枚举值来自真实数据，不硬编码 |
| AC-10 | US-02 | 正常 | date_range 含 current_month/previous_month/month_count |
| AC-11 | US-02 | 正常 | schema_config.json 含所有规定字段，UTF-8 编码 |
| AC-12 | US-02 | 正常 | load_schema_config 有 lru_cache，reload 清缓存 |
| AC-13 | US-02 | 异常 | 配置文件不存在时抛 ConfigNotFoundError 含提示 |
| AC-14 | US-03 | 正常 | /api/schema 返回完整 schema 概览，row_count 实时 |
| AC-15 | US-03 | 正常 | /api/stats 返回 row_count/date_range/channels/first_categories |
| AC-16 | US-03 | 正常 | /api/sample_questions 从 few_shots 取真实问题 |
| AC-17 | US-03 | 边界 | few_shots 不可用时返回 6 条通用兜底问题 |
| AC-18 | US-03 | 正常 | /api/health 返回 status=ok 和当前行数 |
| AC-19 | US-03 | 正常 | /api/llm_status 返回 configured/model/endpoint/describe |
| AC-20 | US-03 | 边界 | schema_config 不存在时 /api/schema fallback 实时扫库 |
