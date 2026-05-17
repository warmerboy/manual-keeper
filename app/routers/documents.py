"""文档 CRUD：列表 / 详情 / 更新元数据（含物理迁移）/ 删除。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..models import DocumentUpdate
from ..services import storage, taxonomy

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_docs(
    category: str | None = None,
    subcategory: str | None = None,
    vendor: str | None = None,
    model: str | None = None,
    needs_review: bool | None = None,
    limit: int = 500,
):
    items = db.list_documents(
        category=category, subcategory=subcategory,
        vendor=vendor, model=model,
        needs_review=needs_review, limit=limit,
    )
    return {"items": items, "count": len(items)}


@router.get("/{doc_id}")
def get_doc(doc_id: int):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    return doc


@router.put("/{doc_id}")
def update_doc(doc_id: int, body: DocumentUpdate):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    payload = body.model_dump(exclude_unset=True)
    tags = payload.pop("tags", None)

    # 把 category 强制收敛到 5 个枚举（兼容历史脏数据）
    if "category" in payload:
        payload["category"] = taxonomy.normalize_category(payload["category"])
    # 大类是"待归档"时清空细类
    if payload.get("category") == taxonomy.UNCLASSIFIED:
        payload["subcategory"] = None

    new_meta = {**doc, **payload}

    # 是否需要迁移文件
    needs_review = new_meta.get("needs_review")
    if needs_review is None:
        # 用户编辑后填了非"待归档"的大类就视为已确认
        cat = new_meta.get("category")
        needs_review = (not cat) or cat == taxonomy.UNCLASSIFIED
        payload["needs_review"] = needs_review
    elif new_meta.get("category") == taxonomy.UNCLASSIFIED:
        # 即使用户传了 needs_review=false，但选了待归档仍然算需要确认
        needs_review = True
        payload["needs_review"] = True

    new_rel = storage.move_to_classified(
        doc["stored_path"],
        new_meta.get("category"),
        new_meta.get("subcategory"),
        new_meta.get("vendor"),
        new_meta.get("model"),
        bool(needs_review),
    )
    payload["stored_path"] = str(new_rel).replace("\\", "/")

    db.update_document(doc_id, payload)
    if tags is not None:
        db.replace_tags(doc_id, tags)
    return db.get_document(doc_id)


@router.delete("/{doc_id}")
def delete_doc(doc_id: int):
    deleted = db.delete_document(doc_id)
    if not deleted:
        raise HTTPException(404, "文档不存在")
    storage.delete_file(deleted["stored_path"])
    return {"ok": True, "id": doc_id}
