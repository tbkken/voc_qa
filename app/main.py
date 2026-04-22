"""VoC 自由问答 FastAPI 服务。

启动:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

主要接口:
    GET  /                 前端页面
    POST /api/ask          自由问答
    POST /api/upload       上传新 CSV
    GET  /api/schema       查看 schema(给前端做提示)
    GET  /api/stats        数据统计
    GET  /api/sample_questions  推荐问题
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import VocEngine
from .llm import LlmClient, LlmConfig
from .pipeline import InsightPipeline, QaPipeline
from .sql_guard import SqlGuard

# ============ 全局对象(启动时初始化) ============
engine = VocEngine()
_llm_config = LlmConfig()
llm = LlmClient(_llm_config)
pipeline = QaPipeline(engine=engine, llm=llm, guard=SqlGuard(max_limit=1000))

# 启动时自动加载样本数据(如存在)
_DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_voc.csv"
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "schema_config.json"

print("=" * 60)
print("🚀 VoC 自由问答服务启动中...")
print("=" * 60)

if _DEFAULT_CSV.exists():
    info = engine.load_csv(_DEFAULT_CSV)
    print(f"📄 数据: 加载 {info['added_rows']:,} 行, 用时 {info['elapsed_sec']}s")
else:
    print("📄 数据: ⚠️ 未找到 data/sample_voc.csv,可通过 /api/upload 上传")

if _CONFIG_PATH.exists():
    try:
        from .config import load_schema_config
        cfg = load_schema_config()
        print(f"📋 配置: {_CONFIG_PATH.name} ({len(cfg['few_shots'])} 个 Few-shot,"
              f"{sum(e['distinct_count'] for e in cfg['enums'].values())} 个枚举值)")
    except Exception as e:
        print(f"📋 配置: ⚠️ 加载失败: {e}")
else:
    print(f"📋 配置: ⚠️ {_CONFIG_PATH.name} 不存在,请运行 `python data/init.py`")

print(f"🤖 {_llm_config.describe()}")

# 代理状态诊断 - 帮助用户识别系统代理是否在影响 LLM 调用
_proxy_vars = {
    "HTTP_PROXY": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
    "HTTPS_PROXY": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
    "NO_PROXY": os.getenv("NO_PROXY") or os.getenv("no_proxy"),
}
_active_proxies = {k: v for k, v in _proxy_vars.items() if v}
if _active_proxies:
    print(f"🌐 系统代理: {_active_proxies}")
    if _llm_config.use_proxy:
        print(f"   LLM_USE_PROXY=1,LLM 调用会走代理")
    else:
        print(f"   ✅ LLM 调用已绕过代理(如需走代理设 LLM_USE_PROXY=1)")
else:
    print(f"🌐 系统代理: 未设置")
print("=" * 60)


# ============ FastAPI App ============
app = FastAPI(title="VoC 声量洞察 · 自由问答", version="1.0.0")

# 允许前端跨域(开发便利)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Schemas ============
class AskRequest(BaseModel):
    question: str


# ============ API 路由 ============
@app.post("/api/ask")
def api_ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    if engine.row_count() == 0:
        raise HTTPException(status_code=400, detail="尚未加载任何数据,请先上传 CSV")

    result = pipeline.ask(req.question)
    return JSONResponse(result.to_dict())


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """上传一个新的 CSV 文件到内存。上传成功后自动重跑 init 刷新配置。"""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="只支持 .csv 文件")

    # 写到 data/uploads 目录(持久化,便于 init.py 读取)
    upload_dir = Path(__file__).resolve().parent.parent / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = upload_dir / file.filename
    with saved.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        info = engine.load_csv(saved)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV 加载失败: {e}")

    # 自动重跑 init 派生新配置
    try:
        from data.init import init as run_init
        run_init(saved, _CONFIG_PATH)
        from .config import reload_schema_config
        reload_schema_config()
        info["config_refreshed"] = True
    except Exception as e:
        info["config_refreshed"] = False
        info["config_error"] = str(e)

    return info


@app.get("/api/llm_status")
def api_llm_status():
    """让前端能显示当前 LLM 配置状态。"""
    return {
        "configured": bool(_llm_config.base_url and _llm_config.api_key),
        "model": _llm_config.model,
        "endpoint": _llm_config.base_url or "(未设置)",
        "describe": _llm_config.describe(),
    }


@app.get("/api/schema")
def api_schema():
    """返回当前数据的 schema 概览(给前端做提示)。"""
    return engine.get_schema_info()


@app.get("/api/stats")
def api_stats():
    """数据基本统计。"""
    schema = engine.get_schema_info()

    # enum 结构是 {distinct_count, top_values: [{value, count}]},展开取 value 列表
    def _enum_values(name):
        e = schema["enums"].get(name)
        if not e:
            return []
        if isinstance(e, dict) and "top_values" in e:
            return [v["value"] for v in e["top_values"]]
        return list(e)  # 兼容 fallback 的老格式

    return {
        "row_count": schema["row_count"],
        "date_range": schema["date_range"],
        "channels": _enum_values("data_channel"),
        "first_categories": _enum_values("first_category"),
    }


@app.get("/api/sample_questions")
def api_sample_questions():
    """推荐提问。优先从 schema_config 的 few_shots 中取真实贴合数据的问题。"""
    try:
        from .config import load_schema_config
        cfg = load_schema_config()
        qs = [fs["question"] for fs in cfg.get("few_shots", [])]
        if qs:
            return {"questions": qs}
    except Exception:
        pass
    # fallback: 通用问题
    return {
        "questions": [
            "TOP 10 负向声量问题是什么?",
            "各渠道声量分布情况?",
            "每月声量趋势?",
            "客服相关的负向投诉 TOP?",
            "情感分布比例?",
            "正向反馈的关键词 TOP 10?",
        ]
    }


@app.post("/api/insight")
def api_insight(req: AskRequest):
    """洞察分析接口，SSE 流式推送各阶段事件。"""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    if engine.row_count() == 0:
        raise HTTPException(status_code=400, detail="尚未加载任何数据，请先上传 CSV")

    def generate():
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        # Step 1: 解析洞察意图
        try:
            parsed = llm.parse_insight_intent(req.question)
        except Exception as e:
            yield sse({"type": "error", "error": f"洞察解析失败: {e}"})
            return

        if not parsed.get("is_insight"):
            yield sse({"type": "error", "error": "未识别为洞察分析请求，请包含「洞察」/「分析以下」等关键词"})
            return

        items: list[str] = parsed.get("items", [])
        if not items:
            yield sse({"type": "error", "error": "未能解析出有效的分析需求，请重新描述（如：分析以下细节：需求1、需求2）"})
            return

        background: str = parsed.get("background", "")

        # Step 2: 推送 init 事件
        yield sse({"type": "init", "total": len(items), "background": background, "items": items})

        # Step 3: 串行处理每条需求
        insight_pl = InsightPipeline(engine=engine, llm=llm, guard=SqlGuard(max_limit=1000))
        successful_items: list[dict] = []

        for event in insight_pl.run(background, items):
            if event["type"] == "all_done":
                break
            yield sse(event)
            if event["type"] == "item_done":
                successful_items.append({"query": items[event["index"]], **event})

        # Step 4: 生成洞察总结
        if not successful_items:
            yield sse({"type": "summary_error", "error": "所有数据需求均分析失败，无法生成洞察总结"})
            return

        failed_count = len(items) - len(successful_items)
        try:
            first_chunk = True
            for chunk in llm.stream_insight_summary(background, successful_items):
                if first_chunk and failed_count > 0:
                    prefix = f"以下洞察基于 {len(successful_items)}/{len(items)} 项成功分析\n\n"
                    yield sse({"type": "summary_chunk", "text": prefix})
                first_chunk = False
                yield sse({"type": "summary_chunk", "text": chunk})
            yield sse({"type": "summary_done"})
        except Exception:
            yield sse({"type": "summary_error", "error": "洞察总结生成失败，但各项分析数据已在下方展示"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "rows": engine.row_count()}


# ============ 前端静态文件 ============
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(_WEB_DIR / "index.html")

    # 静态资源
    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")
