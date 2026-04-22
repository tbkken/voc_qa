"""schema_config.json 加载器。

所有依赖真实数据的配置都从这里走。如果文件不存在,会提示用户先跑 init.py。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "schema_config.json"


class ConfigNotFoundError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_schema_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载 schema_config.json。结果被缓存,init 后需调用 reload_schema_config()。"""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        raise ConfigNotFoundError(
            f"配置文件不存在: {p}\n"
            f"请先运行: python data/init.py <你的CSV路径>"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def reload_schema_config(path: str | Path | None = None) -> dict[str, Any]:
    """强制重新加载配置(data 更新时使用)。"""
    load_schema_config.cache_clear()
    return load_schema_config(path)
