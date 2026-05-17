"""一次性数据迁移：4 层分类 → 2 层分类（v1 → v2）。

启动时调用 `run_migrations()`，幂等：只在 meta.schema_version 还不是 "v2" 时跑。

迁移规则：
- 旧 category == "政策法规"        → 新 category = "规章制度"，subcategory = 旧 subcategory（或"其他"）
- 其他所有 旧 category              → 新 category = "说明书"，subcategory = 旧 category
                                       （把旧的设备大类降格为新的细类）
- vendor / model / doc_type / tags / title / summary 全部保留
- 物理文件按新两层目录重新归位

迁移前自动备份 data/app.db 到 data/app.db.before_v2_<timestamp>.bak
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import db
from .config import db_path, storage_root
from .services import storage, taxonomy

SCHEMA_VERSION_KEY = "schema_version"
TARGET_VERSION = "v2"


def run_migrations() -> None:
    current = db.get_meta(SCHEMA_VERSION_KEY)
    if current == TARGET_VERSION:
        return  # 已经是 v2，无需迁移
    print(f"[migrate] schema_version={current!r} → 开始迁移到 {TARGET_VERSION}")

    _backup_db()
    moved = _migrate_documents()
    db.set_meta(SCHEMA_VERSION_KEY, TARGET_VERSION)
    print(f"[migrate] 完成。迁移 {moved} 份文档")


def _backup_db() -> None:
    src = db_path()
    if not src.exists():
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    dst = src.with_name(f"{src.name}.before_v2_{ts}.bak")
    try:
        shutil.copy2(src, dst)
        print(f"[migrate] 已备份数据库 → {dst.name}")
    except Exception as e:
        print(f"[migrate] 备份数据库失败：{e}")


def _map_old_to_new(old_category: str | None, old_subcategory: str | None) -> tuple[str, str | None]:
    """旧 cat/sub → 新 cat/sub。"""
    if not old_category:
        return taxonomy.UNCLASSIFIED, None

    # 已经是 v2 的 5 个枚举之一 → 不动
    if old_category in taxonomy.CATEGORIES:
        sub = old_subcategory if old_category != taxonomy.UNCLASSIFIED else None
        return old_category, sub

    # 政策法规 → 规章制度
    if old_category == "政策法规":
        sub = old_subcategory or "其他"
        return "规章制度", sub

    # 其他所有（电气设备、家用电器、网络设备、摄影设备等）→ 说明书 / <旧大类作为细类>
    return "说明书", old_category


def _migrate_documents() -> int:
    """遍历所有文档，更新 DB 字段并物理迁移文件。返回迁移的文档数。"""
    rows = db.conn().execute(
        "SELECT id, stored_path, category, subcategory, needs_review FROM documents"
    ).fetchall()

    count = 0
    for row in rows:
        doc_id = row["id"]
        new_cat, new_sub = _map_old_to_new(row["category"], row["subcategory"])

        # 物理迁移：用 storage.move_to_classified 自动算出目标路径
        new_rel = storage.move_to_classified(
            row["stored_path"],
            new_cat,
            new_sub,
            needs_review=bool(row["needs_review"]),
        )

        # 更新 DB
        db.update_document(doc_id, {
            "category": new_cat,
            "subcategory": new_sub,
            "stored_path": str(new_rel).replace("\\", "/"),
        })
        count += 1
        print(f"[migrate]   id={doc_id}: {row['category']}/{row['subcategory']} → {new_cat}/{new_sub}")

    # 清理空的旧目录
    _cleanup_empty_dirs(storage_root() / "files")
    return count


def _cleanup_empty_dirs(root: Path) -> None:
    """递归删除 root 下的空目录（保留 root 自身和 5 个大类的顶层目录）。"""
    if not root.exists():
        return
    keep_top = set(taxonomy.CATEGORIES)  # 5 个大类一级目录始终保留
    # 自底向上扫描
    for path in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: -len(p.parts)):
        # 跳过 root 下一级的 5 个大类目录（即使为空也保留）
        if path.parent == root and path.name in keep_top:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
                print(f"[migrate]   清理空目录 {path.relative_to(storage_root())}")
        except OSError:
            pass
