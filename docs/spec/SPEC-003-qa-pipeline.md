# Spec: 核心问答接口

**Spec 编号**：SPEC-003
**关联 PRD**：VoC 系统初始设计（核心能力）
**版本**：v1.0
**状态**：已确认（补录已上线功能）
**创建日期**：2026-04-23

---

## 背景 & 目标

VoC 系统的核心能力：用户输入自然语言问题 → LLM 生成 SQL → SQL 安全校验 → DuckDB 执行 → LLM 解读结果 → 返回结构化答案（含图表建议）。  
本 Spec 补录该流程中各模块的完整行为约束，包括 `/api/ask` 接口、SqlGuard 安全校验、LLM 客户端弹性策略，以及前端问答 UI。

**非目标**（本期明确不做）：
- 多轮对话记忆（每次 ask 独立无上下文）
- 用户身份鉴权（内网场景不需要）
- SQL 结果缓存

---

## 用户故事与验收标准

### US-01：自然语言问答主流程（/api/ask）

**作为** VoC 分析师，
**我希望** 输入自然语言问题，系统自动查询数据并给出中文答案，
**以便** 不需要懂 SQL 即可从 VoC 数据中获取洞察。

**验收标准**：

- [ ] **AC-01**（正常）：Given 系统已加载数据且 LLM 已配置，When 用户 POST `/api/ask` 带非空 `question` 字段，Then 系统按序执行：(1) LLM 生成 SQL，(2) SqlGuard 安全校验，(3) DuckDB 执行，(4) LLM 解读结果，(5) 推荐图表类型；返回 `AskResult` JSON，字段包含 `question`、`sql`（实际执行的）、`raw_sql`（LLM 原始输出）、`answer`、`data`（含 `columns`、`rows`、`row_count`、`truncated`）、`chart_hint`、`elapsed_ms`，`error` 为 `null`。

- [ ] **AC-02**（正常）：Given 查询执行成功，When 结果行数 > 1000，Then `data.truncated = true`，`data.rows` 只包含前 1000 行，`data.row_count = 1000`。

- [ ] **AC-03**（正常）：Given LLM 结果解读（narrate）调用失败，When 执行成功但 narrate 抛出异常，Then `answer` 字段降级为 `"查询成功，共返回 N 条结果。(结果解读失败: <错误信息>)"`，`error` 仍为 `null`（narrate 失败不影响数据返回）。

- [ ] **AC-04**（异常）：Given 用户提交空字符串问题，When POST `/api/ask`，Then 返回 HTTP 400，`detail = "问题不能为空"`。

- [ ] **AC-05**（异常）：Given 系统尚未加载任何数据（`row_count = 0`），When POST `/api/ask`，Then 返回 HTTP 400，`detail = "尚未加载任何数据，请先上传 CSV"`。

- [ ] **AC-06**（异常）：Given LLM 调用失败（网络异常/超时/鉴权失败），When 执行第一步 generate_sql，Then 返回 `AskResult`，`error` 字段非 null，`answer` 为 `"LLM 调用失败: <原因>"`，`sql` 和 `raw_sql` 均为空字符串。

- [ ] **AC-07**（异常）：Given SQL 经 LLM 生成，When SqlGuard 校验失败，Then 返回 `AskResult`，`error` 非 null，`answer` 为 `"SQL 未通过安全校验: <原因>"`，`sql` 为空字符串，`raw_sql` 为 LLM 原始输出（用于前端 debug 展示）。

- [ ] **AC-08**（异常）：Given SQL 通过 Guard，When DuckDB 执行失败（如 GROUP BY 遗漏），Then 系统调用 `fix_sql` 携带错误上下文让 LLM 修正，修正 SQL 再经 Guard 校验后重试执行；最多尝试 2 次；2 次均失败则返回 `AskResult`，`error` 非 null，`answer` 为 `"SQL 执行失败: <原因>"`。（见 SPEC-001 AC-26 关于 fix_sql 多轮对话细节）

- [ ] **AC-09**（边界）：Given 结果 `rows` 包含 DuckDB 原生 Decimal/date 类型，When 序列化 JSON，Then 这些值统一转为字符串，不出现 JSON 序列化异常。

- [ ] **AC-10**（边界）：Given 查询结果为 0 行，When 推荐图表，Then `chart_hint = "none"`，`data.rows = []`，`answer` 正常由 LLM 解读（LLM 告知无数据）。

---

### US-02：SQL 安全校验（SqlGuard）

**作为** 系统安全策略，
**我希望** 所有 LLM 生成的 SQL 在执行前经过多层安全校验，
**以便** 防止数据篡改、数据泄露或恶意操作。

**验收标准**：

- [ ] **AC-11**（正常）：Given LLM 输出合法的 SELECT 语句（含可选 CTE，即 WITH ... SELECT），When SqlGuard.check() 执行，Then 返回 `GuardResult(ok=True, sql=<处理后 SQL>)`；处理后 SQL 保留原语义，末尾自动追加 `LIMIT 1000`（若原 SQL 尚未含 LIMIT）。

- [ ] **AC-12**（正常）：Given SQL 中含行注释（`--`）或块注释（`/* */`），When SqlGuard.check() 执行，Then 注释被剥除后再执行后续校验，剥除注释不影响 SQL 语义。

- [ ] **AC-13**（异常）：Given LLM 输出含分号（`;`）的多语句，When SqlGuard.check() 执行，Then 返回 `ok=False`，`reason` 说明多语句被拦截；不执行任何 SQL。

- [ ] **AC-14**（异常）：Given LLM 输出非 SELECT/WITH 开头的语句（如 INSERT、UPDATE、DELETE、DROP 等），When SqlGuard.check() 执行，Then 返回 `ok=False`，`reason` 说明只允许 SELECT 查询。

- [ ] **AC-15**（异常）：Given SQL 中包含任意 FORBIDDEN_KEYWORDS（INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE/REPLACE/GRANT/REVOKE/ATTACH/DETACH/COPY/EXPORT/IMPORT/PRAGMA/VACUUM/ANALYZE/INSTALL/LOAD），When SqlGuard.check() 执行，Then 返回 `ok=False`，不论这些关键词出现在何处（函数名内、字符串内均拦截）。

- [ ] **AC-16**（异常）：Given SQL 查询了 `fact_voc` 以外的表（白名单仅含 `fact_voc`），When SqlGuard.check() 执行，Then 返回 `ok=False`，`reason` 说明表不在白名单；不执行查询。

- [ ] **AC-17**（边界）：Given SQL 原本已含 `LIMIT` 子句（如 `LIMIT 5`），When SqlGuard 追加逻辑执行，Then 不再追加第二个 LIMIT，返回的 SQL 保持原有 LIMIT 值。

---

### US-03：LLM 客户端弹性与配置

**作为** 系统运维，
**我希望** LLM 调用在网络抖动或模型超载时自动重试，并支持代理绕过和流式响应，
**以便** 提高用户体验和系统可靠性。

**验收标准**：

- [ ] **AC-18**（正常）：Given LLM 服务返回 502/503/504/408/429 状态码，When LlmClient 发起 HTTP 请求，Then 自动重试，最多重试 `LLM_MAX_RETRIES`（默认 2）次，每次重试间隔按指数退避增加；所有重试失败后抛出异常。

- [ ] **AC-19**（正常）：Given 系统环境变量中存在 `HTTP_PROXY` / `HTTPS_PROXY`，且 `LLM_USE_PROXY=0`（默认值），When LlmClient 发起请求，Then 请求不经过系统代理（设置 `trust_env=False`），直连 `LLM_BASE_URL`。

- [ ] **AC-20**（正常）：Given `LLM_USE_PROXY=1`，When LlmClient 发起请求，Then 请求走系统代理（`trust_env=True`）。

- [ ] **AC-21**（正常）：Given `LLM_STREAM=1`（默认），When `_chat_stream` 调用，Then 使用 SSE 流式协议接收模型输出，逐块 yield 文本，调用方可实时处理。

- [ ] **AC-22**（正常）：Given LLM 响应中包含 `<think>...</think>` 推理标签（DeepSeek-R1/QwQ 等推理模型），When 调用 `generate_sql`、`narrate_result`、`fix_sql`（默认 `strip_think=True`），Then 返回的文本中 think 标签及其内容被完全剥除，调用方收到纯净输出。

- [ ] **AC-23**（边界）：Given `strip_think=False`（`parse_insight_intent` 专用），When LLM 响应含 `<think>` 标签，Then think 标签内容被保留在原始文本中（使 JSON 提取可从 think 块中查找）。

---

### US-04：前端问答聊天 UI

**作为** VoC 分析师，
**我希望** 通过浏览器 UI 以对话方式提问并看到结构化结果，
**以便** 无需工具集成即可使用系统。

**验收标准**：

- [ ] **AC-24**（正常）：Given 前端加载完成，When 用户在输入框输入问题并按 Enter 或点击发送，Then 页面立即显示用户消息气泡，然后显示加载占位；/api/ask 响应返回后，显示助手消息气泡，气泡包含：自然语言答案、SQL 代码块（折叠展示）、数据表格、图表（chart_hint 非 table/none 时）。

- [ ] **AC-25**（正常）：Given 页面首次加载，When `/api/sample_questions` 返回推荐问题列表，Then 问题以标签形式展示在输入框上方；点击任意标签，则该问题填入输入框并立即提交。

- [ ] **AC-26**（正常）：Given 页面首次加载，When `/api/stats` 返回数据统计，Then 导航栏显示当前数据行数和日期范围；When `/api/llm_status` 返回 LLM 配置，Then 导航栏显示已配置的模型名称。

- [ ] **AC-27**（异常）：Given `/api/ask` 返回结果的 `error` 字段非 null，When 前端渲染，Then 显示错误消息气泡，文案为 `answer` 字段内容（含错误描述），不显示图表和数据表格。

- [ ] **AC-28**（边界）：Given 用户点击发送但输入框为空，When 触发提交，Then 不发送请求，不显示消息气泡（本地拦截）。

---

## 数据需求

| 字段名 | 类型 | 说明 | 是否必填 | 关联 AC |
|--------|------|------|----------|---------|
| `question` | str | 用户自然语言问题 | 是 | AC-01、AC-04 |
| `sql` | str | Guard 校验后实际执行的 SQL | 是 | AC-01、AC-07 |
| `raw_sql` | str | LLM 原始输出的 SQL | 是 | AC-01、AC-07 |
| `answer` | str | LLM 自然语言解读 / 错误描述 | 是 | AC-01、AC-03 |
| `data.columns` | list[str] | 查询结果列名 | 是 | AC-01 |
| `data.rows` | list[list] | 查询结果行数据（JSON 安全类型） | 是 | AC-01、AC-09 |
| `data.row_count` | int | 实际返回行数（≤ 1000） | 是 | AC-02 |
| `data.truncated` | bool | 是否因 1000 行限制被截断 | 是 | AC-02 |
| `data.elapsed_ms` | int | DuckDB 执行耗时 | 是 | AC-01 |
| `chart_hint` | str | `metric`/`bar`/`line`/`pie`/`table`/`none` | 是 | AC-01 |
| `elapsed_ms` | int | 全链路总耗时（含 LLM） | 是 | AC-01 |
| `error` | str\|null | 错误信息，成功时为 null | 是 | AC-06、AC-07、AC-08 |

---

## 接口需求

- `POST /api/ask` — 核心问答（关联 US-01：AC-01 ~ AC-10）
  - Request: `{ "question": "..." }`
  - Response: `AskResult` JSON（见数据需求）

---

## 非功能需求

| 类型 | 要求 | 关联 AC |
|------|------|---------|
| 性能 | 非 LLM 部分（Guard + DuckDB）P99 < 100ms | AC-01 |
| 安全 | SqlGuard 必须在 DuckDB 执行前通过，不可绕过 | AC-11 ~ AC-16 |
| 可靠性 | LLM 网络抖动时自动重试，不直接报错给用户 | AC-18 |
| 兼容性 | DuckDB 结果中的非 JSON 类型（Decimal/date）自动转字符串 | AC-09 |

---

## 开放问题（待确认）

无。

---

## AC 汇总表

| AC 编号 | 所属故事 | 类型 | 简述 |
|---------|----------|------|------|
| AC-01 | US-01 | 正常 | 完整问答流程成功，返回 AskResult 全字段 |
| AC-02 | US-01 | 正常 | 结果 >1000 行时 truncated=true，只返回前 1000 行 |
| AC-03 | US-01 | 正常 | narrate 失败时降级文案，不影响数据返回 |
| AC-04 | US-01 | 异常 | 空问题返回 HTTP 400 |
| AC-05 | US-01 | 异常 | 无数据加载时返回 HTTP 400 |
| AC-06 | US-01 | 异常 | LLM 调用失败时 error 非 null |
| AC-07 | US-01 | 异常 | SqlGuard 失败时返回 raw_sql 供 debug |
| AC-08 | US-01 | 异常 | SQL 执行失败自动调用 fix_sql 重试，最多 2 次 |
| AC-09 | US-01 | 边界 | DuckDB 非 JSON 类型统一转字符串 |
| AC-10 | US-01 | 边界 | 0 行结果 chart_hint=none，answer 正常解读 |
| AC-11 | US-02 | 正常 | SELECT/WITH 语句通过校验，自动追加 LIMIT 1000 |
| AC-12 | US-02 | 正常 | SQL 注释被剥除后再校验 |
| AC-13 | US-02 | 异常 | 含分号的多语句被拦截 |
| AC-14 | US-02 | 异常 | 非 SELECT/WITH 开头语句被拦截 |
| AC-15 | US-02 | 异常 | 含 FORBIDDEN_KEYWORDS 被拦截 |
| AC-16 | US-02 | 异常 | 非 fact_voc 表被拦截 |
| AC-17 | US-02 | 边界 | 原 SQL 已含 LIMIT 时不再追加 |
| AC-18 | US-03 | 正常 | 5xx/429/408 自动重试，指数退避，最多 LLM_MAX_RETRIES 次 |
| AC-19 | US-03 | 正常 | LLM_USE_PROXY=0 时直连，不走系统代理 |
| AC-20 | US-03 | 正常 | LLM_USE_PROXY=1 时走系统代理 |
| AC-21 | US-03 | 正常 | LLM_STREAM=1 时使用 SSE 流式接收 |
| AC-22 | US-03 | 正常 | strip_think=True 时 <think> 标签内容被剥除 |
| AC-23 | US-03 | 边界 | strip_think=False 时 <think> 内容保留（用于 JSON 提取） |
| AC-24 | US-04 | 正常 | 提问后显示答案+SQL+表格+图表 |
| AC-25 | US-04 | 正常 | 推荐问题标签点击即提交 |
| AC-26 | US-04 | 正常 | 导航栏显示数据行数、日期范围、LLM 模型名 |
| AC-27 | US-04 | 异常 | error 非 null 时显示错误气泡，不显示图表 |
| AC-28 | US-04 | 边界 | 空输入本地拦截，不发请求 |
