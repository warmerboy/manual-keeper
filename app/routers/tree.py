"""分类树：2 层结构，5 个大类置顶，未使用的大类返回 count=0。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import db
from ..services import taxonomy

router = APIRouter(prefix="/api", tags=["tree"])


@router.get("/tree")
def tree():
    raw = db.category_tree()  # {大类: {__count, children: {细类: count}}}
    active_cats = taxonomy.get_active_categories()

    out = []
    # 按 taxonomy 顺序收集所有大类
    for cat in active_cats:
        node = raw.get(cat, {"__count": 0, "children": {}})
        children = [
            {"name": sub, "count": count}
            for sub, count in sorted(node["children"].items())
        ]
        out.append({"name": cat, "count": node["__count"], "children": children})

    # 兜底：如果 DB 里出现了不在枚举内的旧大类，也展示
    for cat, node in raw.items():
        if cat in active_cats:
            continue
        children = [
            {"name": sub, "count": count}
            for sub, count in sorted(node["children"].items())
        ]
        out.append({"name": cat, "count": node["__count"], "children": children})

    # 按文件数量降序排列（数量多的排前面，空的排最后）
    out.sort(key=lambda x: -x["count"])

    return {"tree": out}
