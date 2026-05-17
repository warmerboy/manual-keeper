"""分类元数据 API：把 5 个大类常量和"建议+已用"细类暴露给前端。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..services import taxonomy as tx

router = APIRouter(prefix="/api/taxonomy", tags=["taxonomy"])


@router.get("/categories")
def list_categories():
    return {"categories": tx.get_active_categories(), "unclassified": tx.UNCLASSIFIED}


@router.get("/subcategories")
def list_subcategories(category: str):
    """返回该大类下『已有用过的细类 ∪ 建议清单』，已有的排前面。"""
    if category not in tx.get_active_categories():
        raise HTTPException(400, f"未知大类：{category}")
    if category == tx.UNCLASSIFIED:
        return {"category": category, "existing": [], "suggested": [], "all": []}
    existing = db.list_subcategories(category)
    suggested = tx.SUGGESTED_SUBCATEGORIES.get(category, [])
    # 合并：已有的优先，建议清单里未出现的接在后面
    existing_set = set(existing)
    merged = list(existing) + [s for s in suggested if s not in existing_set]
    return {
        "category": category,
        "existing": existing,
        "suggested": suggested,
        "all": merged,
    }
