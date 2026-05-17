"""文件落盘：按分类树组织目录，名字做净化避免 Windows 非法字符。"""
from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Tuple

from ..config import storage_root

_INVALID = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_UNCLASSIFIED = "_unclassified"


def sanitize_segment(s: str | None, fallback: str = "_other") -> str:
    if not s:
        return fallback
    s = _INVALID.sub("_", str(s)).strip(" ._-")
    if not s:
        return fallback
    return s[:80]


def build_relative_dir(category: str | None, subcategory: str | None,
                       vendor: str | None, model: str | None,
                       needs_review: bool) -> Path:
    if needs_review or not category:
        return Path("files") / _UNCLASSIFIED
    parts = ["files", sanitize_segment(category)]
    if subcategory:
        parts.append(sanitize_segment(subcategory))
    if vendor:
        parts.append(sanitize_segment(vendor))
    if model:
        parts.append(sanitize_segment(model))
    return Path(*parts)


def absolute(rel: Path | str) -> Path:
    rel = Path(rel)
    return storage_root() / rel


def stash_temp(file_bytes: bytes, original_name: str) -> Tuple[Path, str, str]:
    """先把上传内容写入 _unclassified（带 uuid 前缀），返回 (相对路径, uuid, sha256)。"""
    uid = uuid.uuid4().hex[:12]
    safe_name = sanitize_segment(Path(original_name).stem, fallback="file") + Path(original_name).suffix
    rel = Path("files") / _UNCLASSIFIED / f"{uid}_{safe_name}"
    target = absolute(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(file_bytes)
    sha = hashlib.sha256(file_bytes).hexdigest()
    return rel, uid, sha


def move_to_classified(
    current_rel: Path | str,
    category: str | None,
    subcategory: str | None,
    vendor: str | None,
    model: str | None,
    needs_review: bool,
) -> Path:
    """根据当前元数据迁移文件到正确目录，返回新的相对路径。"""
    cur_abs = absolute(current_rel)
    if not cur_abs.exists():
        return Path(current_rel)
    target_dir_rel = build_relative_dir(category, subcategory, vendor, model, needs_review)
    target_dir_abs = absolute(target_dir_rel)
    target_dir_abs.mkdir(parents=True, exist_ok=True)
    target_abs = target_dir_abs / cur_abs.name
    if target_abs.resolve() == cur_abs.resolve():
        return Path(current_rel)
    # 同名冲突：加 uuid 段
    if target_abs.exists():
        target_abs = target_dir_abs / f"{uuid.uuid4().hex[:6]}_{cur_abs.name}"
    shutil.move(str(cur_abs), str(target_abs))
    return target_abs.relative_to(storage_root())


def delete_file(rel: Path | str) -> None:
    p = absolute(rel)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def absolute_str(rel: Path | str) -> str:
    return str(absolute(rel))
