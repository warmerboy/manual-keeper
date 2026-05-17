"""分类树：2 层结构，5 个大类置顶，未使用的大类返回 count=0。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import db
from ..services import taxonomy

router = APIRouter(prefix="/api", tags=["tree"])


@router.get("/tree")
def tree():
    raw = db.category_tree()  # {大类: {__count, children: {细类: count}}}

    out = []
    # 按 taxonomy 顺序输出 5 个大类（哪怕暂时是空的也展示，方便用户知道有这些大类）
    for cat in taxonomy.CATEGORIES:
        node = raw.get(cat, {"__count": 0, "children": {}})
        children = [
            {"name": sub, "count": count}
            for sub, count in sorted(node["children"].items())
        ]
        out.append({"name": cat, "count": node["__count"], "children": children})

    # 兜底：如果 DB 里出现了不在 5 个枚举内的旧大类（迁移前看到），也展示一下
    for cat, node in raw.items():
        if cat in taxonomy.CATEGORIES:
            continue
        children = [
            {"name": sub, "count": count}
            for sub, count in sorted(node["children"].items())
        ]
        out.append({"name": cat, "count": node["__count"], "children": children})

    return {"tree": out}
