---
name: voc-insight
description: VoC 声量洞察分析 SKILL。接收分析背景 + 数据需求列表，调用 VoC 服务逐条查询，自动选择 Mermaid 图表或 MD 表格，输出完整洞察分析报告（Markdown 格式）。当 Agent 需要对 VoC 数据进行多维洞察、生成结构化分析报告时调用。
---

# VoC 声量洞察 SKILL

## 功能定位

调用 VoC 数据查询服务，将多个数据需求转化为一份 Markdown 格式的洞察分析报告，包含：

- 每条数据需求的查询结果（Mermaid 图表 或 Markdown 表格）
- 每条结果的自然语言解读（来自 VoC 服务 LLM）
- 全局洞察总结（调用 LLM 综合所有数据结论）

**调用方 Agent 负责**：理解用户意图、拆分数据需求列表、调用本 SKILL、将 MD 报告展示给用户。  
**本 SKILL 负责**：数据查询、图表选择与生成、MD 拼装、洞察总结。

---

## 调用方式

```bash
python scripts/generate_report.py \
  --api-url http://localhost:8000 \
  --background "分析上月续航相关问题" \
  --items '["负向声量TOP10问题", "月度声量趋势", "各渠道负向占比"]' \
  [--output report.md]
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--api-url` | 否 | VoC 服务地址，默认读取 `VOC_API_URL` 环境变量，再默认 `http://localhost:8000` |
| `--background` | 否 | 分析背景，拼接到每条数据需求前作为查询上下文 |
| `--items` | 是 | 数据需求列表，JSON 数组字符串，每条是独立可查询的自然语言需求 |
| `--output` | 否 | 输出 MD 文件路径；不填则打印到 stdout |
| `--no-mermaid` | 否 | 禁用 Mermaid，所有图表降级为 MD 表格（用于不支持 Mermaid 的平台） |

### 环境变量

| 变量 | 说明 |
|------|------|
| `VOC_API_URL` | VoC 服务地址 |
| `LLM_BASE_URL` | LLM 接口地址（用于生成洞察总结） |
| `LLM_API_KEY` | LLM API Key |
| `LLM_MODEL` | LLM 模型名，默认 `gpt-4o-mini` |

---

## 图表选择逻辑

SKILL 根据 VoC 服务返回的 `chart_hint` 自动选择渲染方式：

| chart_hint | 渲染方式 | 备注 |
|-----------|---------|------|
| `metric` | MD 粗体数字 | 单行单列数字结果 |
| `pie` | Mermaid `pie` 图 | ≤ 10 个切片，标签截断至 12 字 |
| `bar` | Mermaid `xychart-beta` 柱状 | ≤ 12 条，标签截断至 8 字 |
| `line` | Mermaid `xychart-beta` 折线 | ≤ 24 个时间点，标签截断至 8 字 |
| `table` / `none` | MD 表格 | ≤ 30 行，超出提示总行数 |

---

## 输出示例

```markdown
# VoC 洞察分析报告
_生成时间：2026-04-23 14:30_

**分析背景**：分析上月续航相关问题

---

## 1. 负向声量TOP10问题

xychart-beta
  title "负向声量TOP10问题"
  x-axis ["手机频繁死机", "续航差", ...]
  bar [1234, 987, ...]

> 续航相关负向声量集中在「手机频繁死机」和「续航差」，合计占负向总量的 43%。

<details><summary>SQL</summary>
SELECT fifth_category, COUNT(*) AS cnt FROM fact_voc ...
</details>

---

## 核心洞察总结

本月续航相关投诉以「手机频繁死机」为首，较上月增长 18%...
```

---

## 依赖安装

```bash
pip install httpx
```

---

## Agent 使用指引

1. **拆分数据需求**：从用户输入中识别分析背景（如"上月"/"续航"等条件）和各项独立数据需求，构造 `items` 数组
2. **调用 SKILL**：`python scripts/generate_report.py --background "..." --items '[...]'`
3. **展示结果**：将 stdout 输出的 MD 内容直接返回给用户，或保存为文件后提供下载链接

> 若目标平台不支持 Mermaid 渲染，追加 `--no-mermaid` 参数，所有图表统一降级为 MD 表格。
