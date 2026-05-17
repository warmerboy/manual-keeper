"""文件落盘：按分类树组织目录，名字做净化避免 Windows 非法字符。"""
from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Tuple

from ..config import storage_root
from . import taxonomy

_INVALID = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def sanitize_segment(s: str | None, fallback: str = "_other") -> str:
    if not s:
        return fallback
    s = _INVALID.sub("_", str(s)).strip(" ._-")
    if not s:
        return fallback
    return s[:80]


def build_relative_dir(category: str | None, subcategory: str | None,
                       vendor: str | None = None, model: str | None = None,
                       needs_review: bool = False) -> Path:
    """2 层目录：<大类>/<细类>。

    - 没有 category 或大类是"待归档"或低置信度 → files/待归档/（不分细类）
    - 其余 → files/<大类>/<细类>/（细类缺则归到该大类的"其他"）

    vendor / model 仅作为元数据保留，**不参与目录结构**（v2）。
    """
    # 强制把 category 收敛到 5 个枚举之一
    cat = taxonomy.normalize_category(category)
    if needs_review or cat == taxonomy.UNCLASSIFIED:
        return Path("files") / taxonomy.UNCLASSIFIED
    parts = ["files", sanitize_segment(cat)]
    parts.append(sanitize_segment(subcategory, fallback="其他"))
    return Path(*parts)


def absolute(rel: Path | str) -> Path:
    rel = Path(rel)
    return storage_root() / rel


def stash_temp(file_bytes: bytes, original_name: str) -> Tuple[Path, str, str]:
    """先把上传内容写入"待归档"目录（带 uuid 前缀），返回 (相对路径, uuid, sha256)。"""
    uid = uuid.uuid4().hex[:12]
    safe_name = sanitize_segment(Path(original_name).stem, fallback="file") + Path(original_name).suffix
    rel = Path("files") / taxonomy.UNCLASSIFIED / f"{uid}_{safe_name}"
    target = absolute(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(file_bytes)
    sha = hashlib.sha256(file_bytes).hexdigest()
    return rel, uid, sha


def move_to_classified(
    current_rel: Path | str,
    category: str | None,
    subcategory: str | None,
    vendor: str | None = None,
    model: str | None = None,
    needs_review: bool = False,
) -> Path:
    """根据当前元数据迁移文件到正确目录，返回新的相对路径。

    v2: 只按 category/subcategory 两层。vendor/model 仅作元数据保留，签名兼容。
    """
    cur_abs = absolute(current_rel)
    if not cur_abs.exists():
        return Path(current_rel)
    target_dir_rel = build_relative_dir(category, subcategory, needs_review=needs_review)
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
