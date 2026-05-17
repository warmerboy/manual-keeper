"""上传接口：保存文件 → 抽取文本 → 调 Claude 分类 → 入库 + 物理迁移。"""
from __future__ import annotations

import mimetypes
from typing import List

from fastapi import APIRouter, UploadFile, File

from .. import db
from ..config import CONFIG
from ..services import classify, extract, storage, ocr

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    results = []
    min_conf = float(CONFIG.get("min_confidence", 0.6))

    for f in files:
        try:
            content = await f.read()
            rel_path, uid, sha = storage.stash_temp(content, f.filename or "untitled")
            abs_path = storage.absolute(rel_path)
            extracted = extract.extract(abs_path)
            text = extracted["text"]

            # v2：把现有细类喂给 AI，引导收敛
            known_subs = db.list_subcategories_grouped()
            classified = classify.classify_text(text, f.filename or "", known_subs)
            confidence = float(classified.get("confidence") or 0)
            has_meta = bool(classified.get("category"))
            needs_review = (not has_meta) or confidence < min_conf

            # 根据分类结果移动到最终目录
            new_rel = storage.move_to_classified(
                rel_path,
                classified.get("category"),
                classified.get("subcategory"),
                classified.get("vendor"),
                classified.get("model"),
                needs_review,
            )

            doc_id = db.insert_document({
                "uuid": uid,
                "original_name": f.filename,
                "stored_path": str(new_rel).replace("\\", "/"),
                "mime": f.content_type or mimetypes.guess_type(f.filename or "")[0],
                "size": len(content),
                "sha256": sha,
                "category": classified.get("category"),
                "subcategory": classified.get("subcategory"),
                "vendor": classified.get("vendor"),
                "model": classified.get("model"),
                "doc_type": classified.get("doc_type"),
                "title": classified.get("title") or (f.filename or ""),
                "summary": classified.get("summary"),
                "confidence": confidence,
                "needs_review": needs_review,
                "extracted_text": text,
                "tags": classified.get("tags") or [],
            })

            warn = []
            if not (CONFIG.get("anthropic_api_key") or "").strip():
                warn.append("未配置 ANTHROPIC_API_KEY，仅完成上传，未自动识别")
            if extracted["type"] == "image" and not ocr.available():
                warn.append("Tesseract OCR 未安装，图片暂无法识别文字")
            if needs_review and (CONFIG.get("anthropic_api_key") or "").strip():
                warn.append(f"识别置信度较低（{confidence:.2f}），请人工确认分类")

            results.append({
                "ok": True,
                "id": doc_id,
                "filename": f.filename,
                "needs_review": needs_review,
                "classification": classified,
                "warnings": warn,
            })
        except Exception as e:
            results.append({"ok": False, "filename": f.filename, "error": str(e)})

    return {"results": results}
