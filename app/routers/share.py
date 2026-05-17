"""分享功能路由：隐藏切换、同步到 COS、状态查询。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..services import share

router = APIRouter(prefix="/api/share", tags=["share"])


@router.put("/documents/{doc_id}/hidden")
def toggle_hidden(doc_id: int, hidden: bool = True):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    db.update_document(doc_id, {"hidden": hidden})
    return {"ok": True, "id": doc_id, "hidden": hidden}


@router.post("/sync")
def sync():
    result = share.sync_to_cos()
    return result


@router.get("/status")
def status():
    return share.get_share_status()
