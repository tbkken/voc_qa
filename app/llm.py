"""LLM 客户端 - OpenAI 兼容协议。

环境变量(默认已接真实 LLM,不再是 Mock):
    LLM_BASE_URL    必填。OpenAI 兼容 endpoint,如 https://api.openai.com/v1
                    也可填你的内网 OpenAI 兼容网关,如 https://llm.internal/v1
    LLM_API_KEY     必填。API key(Bearer Token)
    LLM_MODEL       模型名,默认 gpt-4o-mini。阿里/智谱/DeepSeek 等填对应模型名
    LLM_MOCK        设为 1 启用 Mock(无网络、无 key 时的降级方案)
    LLM_TIMEOUT     超时秒数,默认 30

Prompt 的 schema/few-shot 都来自 data/schema_config.json,不再硬编码。
跑 `python data/init.py <csv>` 后,LLM 看到的就是真实数据派生出的提示。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

from .config import load_schema_config


# ============ 配置 ============
@dataclass
class LlmConfig:
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    mock: bool = field(default_factory=lambda: os.getenv("LLM_MOCK", "0") == "1")
    # 默认 300s
    timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "300")))
    # 504/超时自动重试次数
    max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))
    # 流式模式 - 用于应对反向代理的固定超时(如 504 Gateway Timeout)
    # 流式会把 LLM 输出的每个 token 实时推回来,避免代理认为响应太慢
    stream: bool = field(default_factory=lambda: os.getenv("LLM_STREAM", "1") == "1")
    # 是否绕过系统 http_proxy / https_proxy(默认绕过,因为 LLM 通常是内网服务)
    # 如果你的 LLM 必须通过代理访问,设置 LLM_USE_PROXY=1
    use_proxy: bool = field(default_factory=lambda: os.getenv("LLM_USE_PROXY", "0") == "1")

    def describe(self) -> str:
        if self.mock:
            return "LLM: MOCK 模式(关键词匹配)"
        if not self.base_url:
            return "LLM: ⚠️ 未配置 LLM_BASE_URL"
        mode = " [流式]" if self.stream else ""
        proxy = "" if self.use_proxy else " [绕过代理]"
        return f"LLM: {self.model} @ {self.base_url}{mode}{proxy}"


# ============ 客户端 ============
class LlmClient:
    def __init__(self, config: LlmConfig | None = None):
        self.cfg = config or LlmConfig()

    def _chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        """调用 OpenAI 兼容的 /chat/completions。支持流式 (stream=true)。

        流式模式用于应对"反向代理固定超时"场景 - 只要开始流式返回 token,
        大部分代理就不会触发 504。由 LLM_STREAM=1 启用。
        """
        if not self.cfg.base_url or not self.cfg.api_key:
            raise RuntimeError(
                "LLM 未配置,请设置 LLM_BASE_URL 和 LLM_API_KEY,"
                "或设置 LLM_MOCK=1 启用 Mock 模式"
            )
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.cfg.stream:
            payload["stream"] = True

        # 注意:这个网关是 OpenAI Python SDK 的封装,对未知 kwargs 会 500 报错
        # 因此本实现不添加 enable_thinking / chat_template_kwargs 等非标准字段
        # 如果后续接入的网关支持,可以在这里按需添加

        # 重试:504/502/503/超时 自动重试 2 次
        import time as _time
        last_err = None
        # trust_env=False 表示 httpx 不读 HTTP_PROXY/HTTPS_PROXY 等系统环境变量
        # 这是为了避免 LLM(通常是内网服务)被误走公司代理
        trust_env = self.cfg.use_proxy
        for attempt in range(self.cfg.max_retries + 1):
            try:
                if self.cfg.stream:
                    return self._chat_stream(url, headers, payload)
                else:
                    with httpx.Client(timeout=self.cfg.timeout, trust_env=trust_env) as client:
                        r = client.post(url, headers=headers, json=payload)
                        r.raise_for_status()
                        data = r.json()
                        return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                # 只对可恢复的错误重试
                if status in (408, 429, 502, 503, 504) and attempt < self.cfg.max_retries:
                    wait = 2 ** attempt  # 退避 1s, 2s
                    _time.sleep(wait)
                    last_err = f"{status} {e.response.reason_phrase}"
                    continue
                # 其他 HTTP 错误不重试,直接抛友好信息
                raise RuntimeError(
                    f"LLM 服务返回 {status}。可能原因:"
                    + ("反向代理超时(疑似),建议开启流式: export LLM_STREAM=1" if status == 504
                       else "认证失败,请检查 LLM_API_KEY" if status == 401
                       else "请求被拒,请检查 LLM_MODEL 名称" if status == 400
                       else "服务端错误,请检查 LLM 服务日志")
                ) from e
            except httpx.TimeoutException as e:
                if attempt < self.cfg.max_retries:
                    last_err = f"timeout({self.cfg.timeout}s)"
                    _time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    f"LLM 调用超时 ({self.cfg.timeout}s)。"
                    f"考虑: 1) 开启流式 export LLM_STREAM=1; "
                    f"2) 增大 LLM_TIMEOUT"
                ) from e
            except Exception as e:
                raise

        raise RuntimeError(f"LLM 调用重试 {self.cfg.max_retries} 次仍失败,最后错误: {last_err}")

    def _chat_stream(self, url: str, headers: dict, payload: dict) -> str:
        """流式调用。收集所有 delta.content 拼成完整回复。"""
        import json as _json

        content_parts = []
        trust_env = self.cfg.use_proxy
        with httpx.Client(timeout=self.cfg.timeout, trust_env=trust_env) as client:
            with client.stream("POST", url, headers=headers, json=payload) as r:
                # 流式响应可能需要先读取状态码
                if r.status_code != 200:
                    # 读完再抛
                    body = r.read().decode("utf-8", errors="replace")[:500]
                    r.raise_for_status()

                # OpenAI SSE 协议: 每行 "data: {...}" 或 "data: [DONE]"
                for line in r.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(line)
                    except Exception:
                        continue
                    # 提取 delta.content
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    c = delta.get("content")
                    if c:
                        content_parts.append(c)

        return "".join(content_parts)

    # ============ 公开接口 ============
    def generate_sql(self, question: str) -> str:
        """自然语言 -> SQL。Prompt 完全由 schema_config.json 驱动。"""
        if self.cfg.mock:
            return _mock_generate_sql(question)

        schema = load_schema_config()
        system_prompt = build_sql_system_prompt(schema)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        raw = self._chat(messages, temperature=0.05)
        return _extract_sql(raw)

    def narrate_result(self, question: str, sql: str,
                       result: dict[str, Any]) -> str:
        """SQL 查询结果 -> 给人读的自然语言总结。"""
        if self.cfg.mock:
            return _mock_narrate(question, result)

        preview = _result_to_compact_text(result, max_rows=20)
        # 精简 prompt:不传 SQL(对解读没用)、指令更短
        system = "你是数据分析助手。用不超过 150 字的中文总结查询结果:首句结论,引用 TOP1/TOP2 具体数字,点出异常。不要复述问题,不要解释 SQL。"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"问题: {question}\n\n结果:\n{preview}"},
        ]
        return self._chat(messages, temperature=0.3)

    def parse_insight_intent(self, question: str) -> dict:
        """判断是否为洞察分析意图，解析 background 与 items 列表。

        Returns: {is_insight, background, items}
        """
        if self.cfg.mock:
            return _mock_parse_insight(question)

        import json as _json

        system = (
            "判断用户输入是否为「洞察分析」请求，返回 JSON（不加代码块标记）。\n"
            "洞察分析特征：含「洞察」/「数据洞察」/「分析以下」/「分析如下」等触发词，且有多个具体分析需求。\n"
            "格式：{\"is_insight\":true/false,\"background\":\"背景条件(无则空串)\","
            "\"items\":[\"需求1\",\"需求2\"]}\n"
            "非洞察请求返回：{\"is_insight\":false,\"background\":\"\",\"items\":[]}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }
        payload = {"model": self.cfg.model, "messages": messages, "temperature": 0.0}
        trust_env = self.cfg.use_proxy

        try:
            with httpx.Client(timeout=30.0, trust_env=trust_env) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"]
            clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw.strip()).strip()
            result = _json.loads(clean)
            return {
                "is_insight": bool(result.get("is_insight", False)),
                "background": str(result.get("background", "")),
                "items": [s.strip() for s in result.get("items", []) if str(s).strip()],
            }
        except Exception:
            return {"is_insight": False, "background": "", "items": []}

    def stream_insight_summary(self, background: str, successful_items: list) -> Iterator[str]:
        """生成洞察总结，流式 yield 文本块。"""
        if self.cfg.mock:
            yield from _mock_stream_summary(successful_items)
            return

        parts = []
        for idx, item in enumerate(successful_items, 1):
            query = item.get("query", f"分析{idx}")
            narration = item.get("narration", "")
            rows = item.get("rows", [])[:3]
            cols = item.get("columns", [])
            data_snippet = ""
            if rows and cols:
                data_snippet = "；".join(
                    f"{r[0]}={r[-1]}" for r in rows if len(r) >= 2
                )
            parts.append(
                f"【第{idx}项：{query}】\n"
                f"结论：{narration}"
                + (f"\n核心数据：{data_snippet}" if data_snippet else "")
            )

        system = (
            "你是数据洞察专家，根据以下多维度分析数据，提炼 3~5 个核心洞察观点。\n\n"
            "格式要求：\n"
            "- 每个洞察点独立成段\n"
            "- 格式：「观点标题」：一句结论，引用具体数字佐证\n"
            "- 观点清晰有结论性，不泛泛而谈\n"
            "- 直接输出洞察内容，不要引言\n\n"
            "数据来源：\n" + "\n\n".join(parts)
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"背景：{background or '全量数据'}。请提炼核心洞察。"},
        ]
        yield from self._stream_chat_chunks(messages, temperature=0.4)

    def _stream_chat_chunks(self, messages: list, temperature: float = 0.3) -> Iterator[str]:
        """流式调用 LLM，逐 token 块 yield 文本。"""
        import json as _json

        if not self.cfg.base_url or not self.cfg.api_key:
            raise RuntimeError("LLM 未配置，请设置 LLM_BASE_URL 和 LLM_API_KEY")
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        trust_env = self.cfg.use_proxy
        with httpx.Client(timeout=self.cfg.timeout, trust_env=trust_env) as client:
            with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    r.read()
                    r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(line)
                    except Exception:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    c = delta.get("content")
                    if c:
                        yield c


# ============ Prompt 构建(完全数据驱动) ============
def build_sql_system_prompt(schema: dict) -> str:
    """根据 schema_config.json 动态拼装 system prompt。

    可通过环境变量控制 prompt 大小(针对慢模型):
        LLM_MAX_FEWSHOTS  - few-shot 数量 (默认 2)
        LLM_MAX_ENUM_K    - 每个枚举字段展示的 Top-K (默认 15)
    """
    table = schema["table_name"]
    row_count = schema["row_count"]
    dr = schema["date_range"]

    max_fs = int(os.getenv("LLM_MAX_FEWSHOTS", "2"))
    max_enum_k = int(os.getenv("LLM_MAX_ENUM_K", "15"))

    # 字段清单(紧凑化)
    fields_desc = "\n".join(
        f"  - {f['name']}: {f['desc']}"
        for f in schema["fields"]
    )

    # 关键字段的枚举值(截断到 Top-K)
    enum_lines = []
    for field_name, enum_info in schema["enums"].items():
        vals = [v["value"] for v in enum_info["top_values"][:max_enum_k]]
        total = enum_info["distinct_count"]
        suffix = "" if len(vals) >= total else f" ... (共 {total} 个,仅展示 Top{len(vals)})"
        enum_lines.append(f"  - {field_name}: {vals}{suffix}")
    enums_desc = "\n".join(enum_lines)

    # Few-shot 精简到 2 个最关键的
    fs_lines = []
    for i, fs in enumerate(schema["few_shots"][:max_fs], 1):
        fs_lines.append(f"\n示例 {i}:\n问: {fs['question']}\n```sql\n{fs['sql']}\n```")
    few_shots = "".join(fs_lines)

    return f"""你是数据分析师,把中文问题翻译成 DuckDB 的 SELECT SQL。

# 表: {table} ({row_count:,} 行, {dr['min']}~{dr['max']}, 当前月={dr['current_month']}, 上月={dr['previous_month']})

# 字段
{fields_desc}

# 枚举值(真实数据,严格使用,不要虚构)
{enums_desc}

# 规则
1. 只能生成 SELECT / WITH,严禁 INSERT/UPDATE/DELETE/DROP/CREATE
2. 只能查 {table} 表,不要 JOIN
3. pt_d 是 YYYYMMDD 字符串,如 `pt_d >= '20260101'` 或 `SUBSTR(pt_d,1,6)='{dr['current_month']}'`
4. emotion 用完整值如 '负向声量',不要简写
5. 榜单问题加 LIMIT,默认 LIMIT 10
6. 只返回 SQL,用 ```sql ... ``` 包裹,无需解释

# 示例
{few_shots}
"""


# ============ 工具函数 ============
def _extract_sql(text: str) -> str:
    """从 LLM 响应中提取 SQL 代码块。"""
    m = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _result_to_compact_text(result: dict, max_rows: int = 20) -> str:
    cols = result["columns"]
    rows = result["rows"][:max_rows]
    header = " | ".join(cols)
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(" | ".join(str(v) if v is not None else "" for v in r))
    if result.get("row_count", 0) > max_rows:
        lines.append(f"... (共 {result['row_count']} 行,已截断)")
    return "\n".join(lines)


# ============ Mock 兜底 ============
# Mock 现在只作为"无网络/无 key"时的应急手段。
# 规则经过精简,只保留最通用的几条,因为真实 LLM 才是主路径。
_MOCK_RULES: list[tuple[list[str], str]] = [
    (["客服"], """SELECT fifth_category, COUNT(*) AS cnt
FROM fact_voc WHERE first_category = '客户服务' AND emotion = '负向声量'
GROUP BY fifth_category ORDER BY cnt DESC LIMIT 10"""),
    (["渠道"], """SELECT data_channel, COUNT(*) AS total,
       SUM(CASE WHEN emotion='负向声量' THEN 1 ELSE 0 END) AS negative,
       ROUND(100.0 * SUM(CASE WHEN emotion='负向声量' THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_ratio
FROM fact_voc GROUP BY data_channel ORDER BY total DESC"""),
    (["趋势"], """SELECT SUBSTR(pt_d,1,6) AS month, COUNT(*) AS total,
       SUM(CASE WHEN emotion='负向声量' THEN 1 ELSE 0 END) AS negative
FROM fact_voc GROUP BY month ORDER BY month"""),
    (["情感"], """SELECT emotion, COUNT(*) AS cnt,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS ratio
FROM fact_voc GROUP BY emotion ORDER BY cnt DESC"""),
    (["总", "声量"], "SELECT COUNT(*) AS total FROM fact_voc"),
    (["总数"], "SELECT COUNT(*) AS total FROM fact_voc"),
    (["负向"], """SELECT fifth_category, COUNT(*) AS cnt
FROM fact_voc WHERE emotion = '负向声量'
GROUP BY fifth_category ORDER BY cnt DESC LIMIT 10"""),
]


def _mock_generate_sql(question: str) -> str:
    q = question.lower()
    for keywords, sql in _MOCK_RULES:
        if all(kw.lower() in q for kw in keywords):
            return sql
    return """SELECT fifth_category, COUNT(*) AS cnt
FROM fact_voc WHERE emotion = '负向声量'
GROUP BY fifth_category ORDER BY cnt DESC LIMIT 10"""


def _mock_parse_insight(question: str) -> dict:
    TRIGGERS = ["洞察", "分析以下", "分析如下", "数据洞察"]
    if not any(t in question for t in TRIGGERS):
        return {"is_insight": False, "background": "", "items": []}

    bg = ""
    m = re.search(r"对\s*(.{2,20}?)\s*(?:的数据)?[，,]", question)
    if m:
        bg = m.group(1)

    items: list[str] = []
    for trigger in ["分析以下细节：", "分析以下细节:", "分析以下：", "分析以下:",
                    "分析如下细节：", "分析如下：", "分析如下:", "：", ":"]:
        if trigger in question:
            rest = question.split(trigger, 1)[1]
            candidates = [x.strip() for x in re.split(r"[,，、；;\n]", rest) if x.strip()]
            if candidates:
                items = candidates
                break

    if not items:
        items = ["整体声量分布", "负向声量 TOP 品类"]
    return {"is_insight": True, "background": bg, "items": items}


def _mock_stream_summary(successful_items: list) -> Iterator[str]:
    n = len(successful_items)
    text = (
        f"「数据全貌」：本次共分析 {n} 项数据，各维度呈现出清晰的规律特征。\n\n"
        "「头部集中效应」：TOP3 品类合计占据整体负向声量的 60% 以上，"
        "建议优先针对头部问题制定专项改善方案。\n\n"
        "「情感分布不均」：负向声量主要集中在特定品类，"
        "正向声量分布相对分散，说明用户痛点较为集中。\n\n"
        "「时间趋势向好」：近期声量数据呈现积极变化，"
        "建议持续跟踪月度变化，及时捕捉异动信号。"
    )
    for char in text:
        yield char


def _mock_narrate(question: str, result: dict) -> str:
    rows = result["rows"]
    cols = result["columns"]
    if not rows:
        return "查询成功,但没有命中任何数据。可以换个条件试试。"
    if len(rows) == 1 and len(cols) == 1:
        return f"查询结果:{cols[0]} = {rows[0][0]}"
    if len(cols) >= 2 and len(rows) >= 2:
        try:
            top = rows[0]
            val_col = cols[-1]
            n = len(rows)
            total = sum(int(r[-1]) for r in rows
                        if isinstance(r[-1], (int, float))
                        or (isinstance(r[-1], str) and str(r[-1]).replace('.', '').isdigit()))
            parts = [f"共 {n} 条结果,首位是「{top[0]}」,{val_col}={top[-1]}。"]
            if total > 0 and isinstance(top[-1], (int, float)):
                parts.append(f"约占整体 {100.0 * top[-1] / total:.1f}%。")
            if n >= 3:
                parts.append(f"其次「{rows[1][0]}」和「{rows[2][0]}」。")
            return " ".join(parts)
        except Exception:
            pass
    return f"查询完成,共 {len(rows)} 条结果。"
