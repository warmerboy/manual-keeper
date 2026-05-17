"""原文件流式返回，供前端 iframe / 图片标签 / 下载使用。"""
from __future__ import annotations

import mimetypes
import urllib.parse
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .. import db
from ..services import storage

router = APIRouter(tags=["files"])


@router.get("/file/{doc_id}")
def get_file(doc_id: int, download: int = 0):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    abs_path = storage.absolute(doc["stored_path"])
    if not abs_path.exists():
        raise HTTPException(404, "文件已被移动或删除")
    mime = doc.get("mime") or mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream"
    name = doc["original_name"] or abs_path.name
    # RFC 5987 给 Content-Disposition 用，保中文文件名
    quoted = urllib.parse.quote(name)
    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quoted}"}
    return FileResponse(str(abs_path), media_type=mime, headers=headers)
