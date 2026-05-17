"""腾讯云 COS 同步服务：增量上传文件 + 生成访客页面。"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

from ..config import CONFIG, storage_root

VIEWER_TEMPLATE = Path(__file__).resolve().parent.parent / "share_template" / "viewer.html"


def _cos_configured() -> bool:
    return all(
        (CONFIG.get(k) or "").strip()
        for k in ("cos_secret_id", "cos_secret_key", "cos_region", "cos_bucket")
    )


def _get_cos_client():
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=CONFIG["cos_region"],
        SecretId=CONFIG["cos_secret_id"],
        SecretKey=CONFIG["cos_secret_key"],
    )
    return CosS3Client(config)


def _guess_content_type(filename: str) -> str:
    ct, _ = mimetypes.guess_type(filename)
    return ct or "application/octet-stream"


def _upload_text(client, bucket: str, key: str, content: str, content_type: str) -> None:
    """写入临时文件后用 upload_file 上传，确保 Content-Type 正确设置。"""
    suffix = "." + key.rsplit(".", 1)[-1] if "." in key else ""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        client.upload_file(
            Bucket=bucket,
            Key=key,
            LocalFilePath=tmp_path,
            ContentType=content_type,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _cos_key_for_doc(doc: dict[str, Any]) -> str:
    return f"files/{doc['uuid']}_{doc['original_name']}"


def _build_manifest(docs: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for d in docs:
        items.append({
            "uuid": d["uuid"],
            "title": d.get("title") or d["original_name"],
            "original_name": d["original_name"],
            "category": d.get("category"),
            "subcategory": d.get("subcategory"),
            "vendor": d.get("vendor"),
            "model": d.get("model"),
            "doc_type": d.get("doc_type"),
            "summary": d.get("summary"),
            "tags": d.get("tags", []),
            "mime": d.get("mime"),
            "size": d.get("size"),
            "file_key": _cos_key_for_doc(d),
            "updated_at": d.get("updated_at"),
        })
    return {"documents": items, "count": len(items)}


def _password_hash() -> str:
    pwd = (CONFIG.get("share_password") or "").strip()
    if not pwd:
        return ""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def sync_to_cos() -> dict[str, Any]:
    """执行增量同步，返回同步结果摘要。"""
    from .. import db

    if not _cos_configured():
        return {"ok": False, "error": "腾讯云 COS 未配置，请在 config.json 中填写 cos_* 字段"}

    client = _get_cos_client()
    bucket = CONFIG["cos_bucket"]
    files_root = storage_root() / "files"

    uploaded = 0
    deleted = 0
    errors: list[str] = []

    # 1. 上传需要同步的文档（新增或修改过的）
    pending = db.list_pending_sync()
    synced_ids: list[int] = []
    for doc in pending:
        local_path = files_root.parent / doc["stored_path"]
        if not local_path.exists():
            errors.append(f"文件不存在：{doc['original_name']}")
            continue
        cos_key = _cos_key_for_doc(doc)
        content_type = doc.get("mime") or _guess_content_type(doc["original_name"])
        try:
            client.upload_file(
                Bucket=bucket,
                Key=cos_key,
                LocalFilePath=str(local_path),
                ContentType=content_type,
            )
            synced_ids.append(doc["id"])
            uploaded += 1
        except Exception as e:
            errors.append(f"上传失败 {doc['original_name']}：{e}")

    # 2. 删除已隐藏但之前同步过的文档
    hidden_docs = db.list_shared_hidden()
    cleared_ids: list[int] = []
    for doc in hidden_docs:
        cos_key = _cos_key_for_doc(doc)
        try:
            client.delete_object(Bucket=bucket, Key=cos_key)
            cleared_ids.append(doc["id"])
            deleted += 1
        except Exception as e:
            errors.append(f"删除失败 {doc['original_name']}：{e}")

    # 3. 更新数据库时间戳
    db.mark_shared(synced_ids)
    db.clear_shared_at(cleared_ids)

    # 4. 重新生成 manifest.json（全量，包含所有非隐藏文档）
    all_visible = db.list_documents_for_share()
    manifest = _build_manifest(all_visible)
    manifest["password_hash"] = _password_hash()
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
    try:
        _upload_text(client, bucket, "manifest.json", manifest_json, "application/json")
    except Exception as e:
        errors.append(f"上传 manifest.json 失败：{e}")

    # 5. 上传访客页面
    try:
        viewer_html = VIEWER_TEMPLATE.read_text(encoding="utf-8")
        _upload_text(client, bucket, "index.html", viewer_html, "text/html")
    except Exception as e:
        errors.append(f"上传 index.html 失败：{e}")

    return {
        "ok": len(errors) == 0,
        "uploaded": uploaded,
        "deleted": deleted,
        "total_shared": manifest["count"],
        "errors": errors,
    }


def get_share_status() -> dict[str, Any]:
    """返回分享功能的当前状态。"""
    from .. import db

    configured = _cos_configured()
    has_password = bool((CONFIG.get("share_password") or "").strip())

    last_shared = db.conn().execute(
        "SELECT MAX(shared_at) as last FROM documents WHERE shared_at IS NOT NULL"
    ).fetchone()
    last_sync_time = last_shared["last"] if last_shared else None

    shared_count = db.conn().execute(
        "SELECT COUNT(*) as n FROM documents WHERE shared_at IS NOT NULL AND IFNULL(hidden,0)=0"
    ).fetchone()["n"]

    pending_count = db.conn().execute(
        "SELECT COUNT(*) as n FROM documents WHERE IFNULL(hidden,0)=0 "
        "AND (shared_at IS NULL OR updated_at > shared_at)"
    ).fetchone()["n"]

    return {
        "cos_configured": configured,
        "has_password": has_password,
        "last_sync_time": last_sync_time,
        "shared_count": shared_count,
        "pending_count": pending_count,
    }
