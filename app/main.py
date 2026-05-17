"""FastAPI 入口：装配路由、首启建表、提供首页模板。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import db, migrate
from .config import CONFIG
from .routers import documents, files, reorganize as reorganize_router, search, taxonomy as taxonomy_router, tree, upload

BASE = Path(__file__).resolve().parent

app = FastAPI(title="说明书保管箱", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

app.include_router(upload.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(tree.router)
app.include_router(files.router)
app.include_router(taxonomy_router.router)
app.include_router(reorganize_router.router)


@app.on_event("startup")
def _startup():
    # 触发 DB 初始化
    _ = db.conn()
    # v1 → v2 数据迁移（幂等）
    migrate.run_migrations()
    if not (CONFIG.get("anthropic_api_key") or "").strip():
        print("[启动] 未检测到 ANTHROPIC_API_KEY，自动识别功能将关闭；可上传后手动打标签。")
    else:
        print(f"[启动] 使用模型：{CONFIG.get('model')}")
    print(f"[启动] 访问 http://127.0.0.1:{CONFIG.get('port', 8765)}")


_INDEX_HTML = (BASE / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_INDEX_HTML)


@app.get("/api/status")
def status():
    from .services import ocr
    return {
        "api_key_configured": bool((CONFIG.get("anthropic_api_key") or "").strip()),
        "model": CONFIG.get("model"),
        "ocr_available": ocr.available(),
        "min_confidence": CONFIG.get("min_confidence"),
    }
