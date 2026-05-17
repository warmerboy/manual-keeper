"""文档 CRUD：列表 / 详情 / 更新元数据（含物理迁移）/ 删除。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..models import DocumentUpdate
from ..services import storage

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

    # 是否需要迁移文件
    new_meta = {**doc, **payload}
    needs_review = new_meta.get("needs_review")
    if needs_review is None:
        # 用户编辑后填了 category 则视为已确认
        needs_review = not bool(new_meta.get("category"))
        payload["needs_review"] = needs_review

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
