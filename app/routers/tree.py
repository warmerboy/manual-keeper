"""分类树：嵌套字典转 sidebar 友好的 JSON。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import db

router = APIRouter(prefix="/api", tags=["tree"])


def _to_node(name: str, payload):
    """递归把内部嵌套字典转成 [{name, count, children: [...]}, ...]"""
    if isinstance(payload, dict) and "children" in payload:
        children = []
        for k, v in sorted(payload["children"].items()):
            children.append(_to_node(k, v))
        return {"name": name, "count": payload["__count"], "children": children}
    # 最后一层：型号 -> count
    return {"name": name, "count": int(payload), "children": []}


@router.get("/tree")
def tree():
    raw = db.category_tree()
    out = []
    for k, v in sorted(raw.items()):
        out.append(_to_node(k, v))
    return {"tree": out}
