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
        if not self.base_url:
            return "LLM: ⚠️ 未配置 LLM_BASE_URL"
        mode = " [流式]" if self.stream else ""
        proxy = "" if self.use_proxy else " [绕过代理]"
        return f"LLM: {self.model} @ {self.base_url}{mode}{proxy}"


# ============ 客户端 ============
class LlmClient:
    def __init__(self, config: LlmConfig | None = None):
        self.cfg = config or LlmConfig()

    def _chat(self, messages: list[dict], temperature: float = 0.1,
              strip_think: bool = True) -> str:
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
                    return self._chat_stream(url, headers, payload, strip_think=strip_think)
                else:
                    with httpx.Client(timeout=self.cfg.timeout, trust_env=trust_env) as client:
                        r = client.post(url, headers=headers, json=payload)
                        r.raise_for_status()
                        data = r.json()
                        content = data["choices"][0]["message"]["content"]
                        if strip_think:
                            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                        return content
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

    def _chat_stream(self, url: str, headers: dict, payload: dict,
                     strip_think: bool = True) -> str:
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

        result = "".join(content_parts)
        if strip_think:
            result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
        return result

    # ============ 公开接口 ============
    def generate_sql(self, question: str) -> str:
        """自然语言 -> SQL。Prompt 完全由 schema_config.json 驱动。"""
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
        """SQL 查询结果 -> 给人读的自然语言总结。严格基于表格数据，禁止幻觉。"""
        preview = _result_to_compact_text(result, max_rows=20)
        row_count = result.get("row_count", 0)
        system = (
            "你是数据分析助手。根据下方【查询结果表格】写一段不超过 150 字的中文总结。\n\n"
            "硬性要求：\n"
            "- 所有数字、排名、占比必须直接引用表格中的原始数值，严禁凭经验或常识编造\n"
            "- 首句给出核心结论，引用表格中 TOP1/TOP2 的具体数值\n"
            f"- 表格共 {row_count} 行；若为 0 行，只说「未查询到符合条件的数据」，不给任何推断\n"
            "- 严禁使用「通常」「一般」「可能」「预计」「往往」等推测性表述\n"
            "- 不复述问题，不解释 SQL"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"问题: {question}\n\n【查询结果表格】\n{preview}"},
        ]
        return self._chat(messages, temperature=0.1)

    def parse_insight_intent(self, question: str) -> dict:
        """用 LLM 从用户输入中提取背景条件和数据需求列表。

        不预先剥离 think 标签：推理模型可能把 JSON 放在 <think> 块内，
        剥离后 JSON 丢失是之前 fallback 到单条的根因。
        分三层搜索 JSON：think 块外 → think 块内 → 全文。
        LLM 失败时先尝试按"？"分割，再降级单条。
        """
        import json as _json

        messages = [
            {"role": "system", "content": (
                "从用户输入中提取所有独立的数据分析需求，只返回 JSON，不要代码块符号，不要任何解释。\n"
                '格式：{"background": "通用背景条件（时间/产品范围等，无则空字符串）", '
                '"items": ["需求1", "需求2", ...]}\n\n'
                "规则：\n"
                "- 每个可以独立查询的问题/需求单独作为一条 item\n"
                "- 问号（？/?）、句号、分号、换行均可作为独立需求边界\n"
                "- background 是所有 items 共享的背景条件，不重复放进 items\n"
                "- 只有 1 个需求时 items 也是单元素列表"
            )},
            {"role": "user", "content": question},
        ]
        raw = None
        try:
            # strip_think=False：保留完整原始响应，确保 JSON 在 think 块内时也能找到
            raw = self._chat(messages, temperature=0.1, strip_think=False)
            print(f"[parse_insight_intent] raw={raw[:400]!r}")

            def _extract_items(text: str):
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if not m:
                    return None
                data = _json.loads(m.group())
                items = [str(x).strip() for x in data.get("items", []) if str(x).strip()]
                return (data.get("background", ""), items) if items else None

            # 层 1：think 块之外
            outside = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
            result = _extract_items(outside)

            # 层 2：think 块内部（逐块搜索）
            if not result:
                for block in re.findall(r"<think>(.*?)</think>", raw, re.DOTALL):
                    result = _extract_items(block)
                    if result:
                        break

            # 层 3：全文（不区分 think 边界）
            if not result:
                result = _extract_items(raw)

            if result:
                bg, items = result
                print(f"[parse_insight_intent] LLM 识别到 {len(items)} 条需求")
                return {"is_insight": True, "background": bg, "items": items}

        except Exception as e:
            print(f"[parse_insight_intent] LLM 解析失败: {e}, raw={str(raw)[:300] if raw else 'None'}")

        # 兜底 1：按中英文问号分割（比单条更准确）
        q_items = [x.strip() for x in re.split(r'[？?]+', question) if x.strip() and len(x.strip()) > 2]
        if len(q_items) > 1:
            print(f"[parse_insight_intent] 问号分割兜底: {len(q_items)} 条")
            return {"is_insight": True, "background": "", "items": q_items}

        # 兜底 2：单条
        return {"is_insight": True, "background": "", "items": [question.strip()]}

    def stream_insight_summary(self, background: str, successful_items: list) -> Iterator[str]:
        """生成洞察总结，流式 yield 文本块。"""
        parts = []
        for idx, item in enumerate(successful_items, 1):
            query = item.get("query", f"分析{idx}")
            narration = item.get("narration", "")
            rows = item.get("rows", [])
            cols = item.get("columns", [])
            # 传入完整表格（最多 20 行），确保总结 LLM 能看到真实数据
            table_text = ""
            if cols and rows:
                header = " | ".join(cols)
                data_lines = [header, "-" * len(header)]
                for r in rows[:20]:
                    data_lines.append(" | ".join(str(v) if v is not None else "" for v in r))
                if len(rows) > 20:
                    data_lines.append(f"... 共 {len(rows)} 行，已截断")
                table_text = "\n".join(data_lines)
            parts.append(
                f"【第{idx}项：{query}】\n"
                f"叙述：{narration}"
                + (f"\n原始数据：\n{table_text}" if table_text else "\n（无数据）")
            )

        system = (
            "你是资深用户声量（VoC）分析专家，正在为管理层撰写洞察报告。\n\n"
            "请基于以下各维度的【原始数据表格】，直接输出 3~5 个核心洞察观点。\n\n"
            "格式（每个观点独立成段，段间空一行）：\n"
            "「观点标题」：核心结论一句话，引用具体数值/占比/排名佐证。\n\n"
            "硬性要求：\n"
            "- 所有引用的数字必须来自下方原始数据，严禁凭先验知识编造\n"
            "- 每个结论必须有具体数据支撑，禁止模糊表述\n"
            "- 语言专业简洁，高管报告风格\n"
            "- 直接从第一个「观点」开始输出，禁止任何引言、推理过程、<think> 内容和收尾总结\n\n"
            "数据来源：\n" + "\n\n".join(parts)
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"背景：{background or '全量数据'}。请提炼核心洞察。"},
        ]
        yield from _strip_think_tags(self._stream_chat_chunks(messages, temperature=0.4))

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



def _strip_think_tags(chunks: Iterator[str]) -> Iterator[str]:
    """Filter out <think>...</think> blocks from a streaming chunk iterator.

    Handles tags split across multiple chunks with a state-machine buffer.
    """
    buffer = ""
    in_think = False
    for chunk in chunks:
        buffer += chunk
        while True:
            if not in_think:
                start = buffer.find("<think>")
                if start == -1:
                    # No opening tag — safe to yield everything except a partial-tag tail
                    safe_len = max(0, len(buffer) - len("<think>"))
                    if safe_len:
                        yield buffer[:safe_len]
                        buffer = buffer[safe_len:]
                    break
                if start > 0:
                    yield buffer[:start]
                buffer = buffer[start:]
                in_think = True
            else:
                end = buffer.find("</think>")
                if end == -1:
                    break  # Still inside <think>, wait for more chunks
                buffer = buffer[end + len("</think>"):]
                in_think = False
    # Flush remaining content (only if not inside an unclosed <think>)
    if buffer and not in_think:
        yield buffer



