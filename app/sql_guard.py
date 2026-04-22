"""SQL 安全校验 - 核心原则:只允许 SELECT,禁止一切写/DDL。

LLM 生成的 SQL 必须通过这里才能执行。这是防御 LLM 出错或被 prompt injection
攻击的最后一道防线。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# 绝对禁用的关键词(大小写不敏感,带词边界匹配)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE",
    "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH", "COPY", "EXPORT",
    "IMPORT", "PRAGMA", "VACUUM", "ANALYZE",
    # DuckDB 特有的危险操作
    "INSTALL", "LOAD",
}

# 允许引用的表名 - 限制 LLM 只能查我们的数据
ALLOWED_TABLES = {"fact_voc"}


@dataclass
class GuardResult:
    ok: bool
    sql: str            # 规范化/加上 LIMIT 后的 SQL
    reason: str = ""    # 失败原因


class SqlGuard:
    """
    SQL 安全校验器。策略:
    - 只允许以 SELECT 或 WITH 开头
    - 禁止多条语句(不能含分号后再跟其他语句)
    - 黑名单关键词检查(词边界)
    - 表名白名单检查
    - 强制追加 LIMIT(如果没有)
    """

    def __init__(self, max_limit: int = 1000) -> None:
        self.max_limit = max_limit

    def check(self, sql: str) -> GuardResult:
        if not sql or not sql.strip():
            return GuardResult(False, "", "SQL 为空")

        # 去掉注释(-- 和 /* */)
        cleaned = _strip_comments(sql).strip().rstrip(";").strip()

        # 1. 不允许多语句
        if ";" in cleaned:
            return GuardResult(False, sql, "不允许多条 SQL 语句")

        # 2. 必须以 SELECT 或 WITH 开头
        first_word = cleaned.split(None, 1)[0].upper() if cleaned.split() else ""
        if first_word not in ("SELECT", "WITH"):
            return GuardResult(False, sql, f"只允许 SELECT/WITH 查询,不允许 {first_word}")

        # 3. 黑名单关键词
        upper = cleaned.upper()
        for kw in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{kw}\b", upper):
                return GuardResult(False, sql, f"SQL 中包含禁用关键词: {kw}")

        # 4. 表名白名单 - 粗略提取 FROM/JOIN 后的 identifier
        tables = _extract_table_refs(cleaned)
        bad = tables - ALLOWED_TABLES
        if bad:
            return GuardResult(False, sql, f"不允许访问的表: {', '.join(sorted(bad))}")

        # 5. 追加 LIMIT(如果外层 SELECT 没有)
        final_sql = _ensure_limit(cleaned, self.max_limit)

        return GuardResult(True, final_sql, "")


def _strip_comments(sql: str) -> str:
    """去除 -- 行注释和 /* */ 块注释。"""
    # 块注释
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # 行注释
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def _extract_table_refs(sql: str) -> set[str]:
    """粗略提取 FROM/JOIN 后引用的表名。对 CTE 会宽松一点,允许 WITH 中的别名。"""
    refs = set()
    # 匹配 FROM 和 JOIN 后的第一个标识符
    for m in re.finditer(r"\b(FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.IGNORECASE):
        refs.add(m.group(2).lower())

    # CTE 别名需要从白名单剔除前加入(WITH alias AS (...))
    cte_names = set()
    for m in re.finditer(r"\bWITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql, re.IGNORECASE):
        cte_names.add(m.group(1).lower())
    for m in re.finditer(r",\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql, re.IGNORECASE):
        cte_names.add(m.group(1).lower())

    return refs - cte_names


def _ensure_limit(sql: str, max_limit: int) -> str:
    """如果 SQL 最外层没有 LIMIT,追加一个。"""
    if re.search(r"\bLIMIT\s+\d+\s*$", sql, re.IGNORECASE):
        return sql
    return f"{sql} LIMIT {max_limit}"
