"""全文搜索：FTS5。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import db

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(q: str = "", limit: int = 100):
    items = db.search_documents(q, limit=limit)
    return {"items": items, "count": len(items), "q": q}
