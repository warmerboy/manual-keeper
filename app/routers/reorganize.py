"""一键重整 API：状态 / 预览 / 应用 / 回滚。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..services import reorganize

router = APIRouter(prefix="/api/reorganize", tags=["reorganize"])


@router.get("/status")
def status():
    """查询是否有可回退的快照，给 UI 决定是否显示回退按钮。"""
    raw = db.get_meta(reorganize.REORG_SNAPSHOT_KEY)
    if not raw:
        return {"has_snapshot": False}
    try:
        snap = json.loads(raw)
    except Exception:
        return {"has_snapshot": False}
    return {
        "has_snapshot": True,
        "snapshot_saved_at": snap.get("saved_at"),
        "last_reorg_at": db.get_meta(reorganize.LAST_REORG_AT_KEY),
        "doc_count": len(snap.get("documents", [])),
    }


class ApplyBody(BaseModel):
    new_categories: list[str]
    assignments: list[dict]


@router.post("/preview")
def preview():
    """调 AI 生成方案，但不落地。"""
    result = reorganize.propose()
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "生成方案失败"))
    return result


@router.post("/apply")
def apply(body: ApplyBody):
    """落地用户确认后的方案。"""
    result = reorganize.apply({
        "new_categories": body.new_categories,
        "assignments": body.assignments,
    })
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "应用失败"))
    return result


@router.post("/rollback")
def rollback():
    """从上次快照回滚。"""
    result = reorganize.rollback()
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "回滚失败"))
    return result
