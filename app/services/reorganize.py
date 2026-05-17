"""一键重整：基于所有文档的极简摘要，让 AI 重新设计『大类 + 细类』。

设计要点：
- 仅读取每份文档的 reorg_summary（缺失时退回到 summary），不读原文，控制 token
- AI 输出必须含 6-10 个大类，且必须保留『待归档』
- 返回 proposal 给前端预览；用户确认后再 apply
- apply 前保存当前快照到 meta.last_reorg_snapshot，支持回滚
"""
from __future__ import annotations

import json
import time
from typing import Any

from .. import db
from ..config import CONFIG
from . import storage, taxonomy

REORG_SNAPSHOT_KEY = "last_reorg_snapshot"
LAST_REORG_AT_KEY = "last_reorg_at"


def _build_prompt(docs: list[dict]) -> str:
    """把所有文档摘要拼成给 AI 的上下文。"""
    lines = [
        "你是一个个人技术资料分类咨询顾问。下面是用户的所有文档清单（含当前的分类和极简摘要）。",
        "请基于这些信息，对整体分类做一次智能优化：合并近义大类、规整命名、确保每份文档分到合适的位置。",
        "",
        "## 约束（必须遵守）",
        "1. 新大类总数建议 **6-10 个**（留出冗余应对未来文档），不可少于 4 个、不可多于 12 个",
        "2. 「待归档」三个字必须**原封不动**保留作为兜底大类（不可改名、不可删除），但只放确实分不出来的文档",
        "3. 每份文档必须分到一个大类（含『待归档』）",
        "4. 大类命名要简洁通用（2-6 字），涵盖范围要广，避免过细",
        "5. 细类命名也要简洁，能合并就合并、复用就复用，不要为单个文档造细类",
        "6. 即便当前文档不多，也要考虑常见的资料类型（电子书、软件文档、生活规则、教程等）预留大类",
        "",
        "## 文档清单",
    ]
    for d in docs:
        cur = f"{d.get('category') or '?'}/{d.get('subcategory') or '?'}"
        meta = []
        if d.get("vendor"):
            meta.append(f"厂商={d['vendor']}")
        if d.get("model"):
            meta.append(f"型号={d['model']}")
        if d.get("doc_type"):
            meta.append(f"类型={d['doc_type']}")
        meta_str = "  ".join(meta)
        title = d.get("title") or ""
        compact = (d.get("compact_summary") or "").strip()
        lines.append(f"[id={d['id']}] 现={cur}  标题=「{title}」  {meta_str}")
        if compact:
            lines.append(f"          摘要：{compact}")
    lines += [
        "",
        "请通过 reorganize 工具返回新方案。"
    ]
    return "\n".join(lines)


REORGANIZE_TOOL = {
    "name": "reorganize",
    "description": "返回新的分类体系和每份文档的新归属。",
    "input_schema": {
        "type": "object",
        "properties": {
            "new_categories": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 4,
                "maxItems": 12,
                "description": "新大类清单。**必须包含『待归档』**。建议 6-10 个，且预留常见资料类型",
            },
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "integer"},
                        "category": {"type": "string", "description": "必须在 new_categories 中"},
                        "subcategory": {"type": ["string", "null"], "description": "大类是『待归档』时填 null"},
                    },
                    "required": ["doc_id", "category"],
                },
                "description": "每份文档的新分类。doc_id 必须覆盖输入的所有文档",
            },
            "rationale": {
                "type": "string",
                "maxLength": 400,
                "description": "200 字以内说明这次重整的整体逻辑，例如『把音视频和摄影合并因为...』",
            },
        },
        "required": ["new_categories", "assignments", "rationale"],
    },
}


def propose() -> dict[str, Any]:
    """调 AI 生成方案。返回的 dict 包含：
    {
      ok, reason?: str,
      new_categories, assignments, rationale, current_categories,
      diff: { categories_added, categories_removed, docs_moved }
    }
    """
    api_key = (CONFIG.get("anthropic_api_key") or "").strip()
    if not api_key:
        return {"ok": False, "reason": "未配置 ANTHROPIC_API_KEY，无法调用 AI"}

    docs = db.list_for_reorg()
    if not docs:
        return {"ok": False, "reason": "目前还没有任何文档，不需要重整"}

    prompt = _build_prompt(docs)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CONFIG.get("model", "claude-haiku-4-5"),
            max_tokens=4096,
            tools=[REORGANIZE_TOOL],
            tool_choice={"type": "tool", "name": "reorganize"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return {"ok": False, "reason": f"AI 调用失败：{e}"}

    data = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "reorganize":
            data = block.input or {}
            break
    if not data:
        return {"ok": False, "reason": "AI 没有返回 reorganize 工具调用"}

    new_cats = data.get("new_categories") or []
    assignments = data.get("assignments") or []
    rationale = data.get("rationale") or ""

    # 强制保留待归档
    if taxonomy.UNCLASSIFIED not in new_cats:
        new_cats = list(new_cats) + [taxonomy.UNCLASSIFIED]

    # 校验 assignments 都用合法 category
    valid_cats = set(new_cats)
    for a in assignments:
        if a.get("category") not in valid_cats:
            a["category"] = taxonomy.UNCLASSIFIED
            a["subcategory"] = None
        if a.get("category") == taxonomy.UNCLASSIFIED:
            a["subcategory"] = None

    # 计算 diff（用于 UI 预览）
    current_cats = taxonomy.get_active_categories()
    current_cats_set = set(current_cats)
    new_cats_set = set(new_cats)
    cur_map = {d["id"]: (d.get("category"), d.get("subcategory")) for d in docs}

    moved = []
    for a in assignments:
        did = a["doc_id"]
        if did not in cur_map:
            continue
        cur_cat, cur_sub = cur_map[did]
        new_cat, new_sub = a.get("category"), a.get("subcategory")
        if (cur_cat, cur_sub) != (new_cat, new_sub):
            moved.append({
                "doc_id": did,
                "title": next((d.get("title") for d in docs if d["id"] == did), ""),
                "from": f"{cur_cat or '?'} / {cur_sub or '?'}",
                "to": f"{new_cat} / {new_sub or '(无细类)'}",
            })

    return {
        "ok": True,
        "new_categories": new_cats,
        "assignments": assignments,
        "rationale": rationale,
        "current_categories": current_cats,
        "diff": {
            "categories_added": sorted(new_cats_set - current_cats_set),
            "categories_removed": sorted(current_cats_set - new_cats_set),
            "docs_moved": moved,
            "docs_total": len(docs),
            "docs_moved_count": len(moved),
        },
    }


def apply(proposal: dict[str, Any]) -> dict[str, Any]:
    """落地：保存快照 → 更新 active_categories → 更新每份文档 → 物理迁移文件。"""
    new_cats = proposal.get("new_categories") or []
    assignments = proposal.get("assignments") or []
    if not new_cats or not assignments:
        return {"ok": False, "reason": "提案数据不完整"}
    if taxonomy.UNCLASSIFIED not in new_cats:
        new_cats = list(new_cats) + [taxonomy.UNCLASSIFIED]

    # 1) 保存当前快照
    current_docs = db.list_for_reorg()
    snapshot = {
        "active_categories": taxonomy.get_active_categories(),
        "documents": [
            {"id": d["id"], "category": d["category"], "subcategory": d["subcategory"]}
            for d in current_docs
        ],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.set_meta(REORG_SNAPSHOT_KEY, json.dumps(snapshot, ensure_ascii=False))

    # 2) 更新 active_categories
    taxonomy.set_active_categories(new_cats)

    # 3) 更新每份文档 + 物理迁移
    moved_files = 0
    errors = []
    for a in assignments:
        doc_id = a.get("doc_id")
        new_cat = a.get("category")
        new_sub = a.get("subcategory")
        doc = db.get_document(doc_id)
        if not doc:
            errors.append(f"id={doc_id} 文档不存在")
            continue
        try:
            new_rel = storage.move_to_classified(
                doc["stored_path"],
                new_cat,
                new_sub,
                needs_review=(new_cat == taxonomy.UNCLASSIFIED),
            )
            db.update_document(doc_id, {
                "category": new_cat,
                "subcategory": new_sub,
                "stored_path": str(new_rel).replace("\\", "/"),
                "needs_review": new_cat == taxonomy.UNCLASSIFIED,
            })
            moved_files += 1
        except Exception as e:
            errors.append(f"id={doc_id} 迁移失败：{e}")

    db.set_meta(LAST_REORG_AT_KEY, time.strftime("%Y-%m-%d %H:%M:%S"))

    return {
        "ok": True,
        "moved_files": moved_files,
        "new_categories": new_cats,
        "errors": errors,
    }


def rollback() -> dict[str, Any]:
    """从上次快照回滚。**消费式**：成功后清空快照，避免误操作连续回退。"""
    raw = db.get_meta(REORG_SNAPSHOT_KEY)
    if not raw:
        return {"ok": False, "reason": "没有可回滚的快照"}
    try:
        snap = json.loads(raw)
    except Exception:
        return {"ok": False, "reason": "快照已损坏"}

    taxonomy.set_active_categories(snap.get("active_categories", []))
    moved = 0
    for d in snap.get("documents", []):
        doc = db.get_document(d["id"])
        if not doc:
            continue
        new_rel = storage.move_to_classified(
            doc["stored_path"],
            d.get("category"),
            d.get("subcategory"),
            needs_review=(d.get("category") == taxonomy.UNCLASSIFIED),
        )
        db.update_document(d["id"], {
            "category": d.get("category"),
            "subcategory": d.get("subcategory"),
            "stored_path": str(new_rel).replace("\\", "/"),
        })
        moved += 1

    # 消费快照：避免连续回退
    db.set_meta(REORG_SNAPSHOT_KEY, "")
    return {"ok": True, "moved_files": moved, "restored_at": snap.get("saved_at")}
