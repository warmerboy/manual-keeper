"""SQLite 数据访问层：documents + tags + FTS5 全文索引。"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from .config import db_path

_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


_CONN: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = _connect()
        init_schema(_CONN)
    return _CONN


@contextmanager
def tx():
    with _LOCK:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime TEXT,
    size INTEGER,
    sha256 TEXT,
    category TEXT,
    subcategory TEXT,
    vendor TEXT,
    model TEXT,
    doc_type TEXT,
    title TEXT,
    summary TEXT,
    confidence REAL DEFAULT 0,
    needs_review INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extracted_text TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, summary, extracted_text, original_name, vendor, model, tags_concat,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def init_schema(c: sqlite3.Connection) -> None:
    c.executescript(SCHEMA)
    c.commit()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tags_concat(c: sqlite3.Connection, doc_id: int) -> str:
    rows = c.execute(
        "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id=t.id WHERE dt.document_id=?",
        (doc_id,),
    ).fetchall()
    return " ".join(r["name"] for r in rows)


def _reindex_fts(c: sqlite3.Connection, doc_id: int) -> None:
    """重建该文档在 documents_fts 中的行（先删后插，避免 rowid 冲突）。"""
    c.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
    row = c.execute(
        "SELECT title, summary, extracted_text, original_name, vendor, model FROM documents WHERE id=?",
        (doc_id,),
    ).fetchone()
    if row is None:
        return
    tags_str = _tags_concat(c, doc_id)
    c.execute(
        "INSERT INTO documents_fts(rowid, title, summary, extracted_text, original_name, vendor, model, tags_concat) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_id,
            row["title"] or "",
            row["summary"] or "",
            row["extracted_text"] or "",
            row["original_name"] or "",
            row["vendor"] or "",
            row["model"] or "",
            tags_str,
        ),
    )


def insert_document(data: dict[str, Any]) -> int:
    with tx() as c:
        now = _now()
        cur = c.execute(
            """
            INSERT INTO documents
              (uuid, original_name, stored_path, mime, size, sha256,
               category, subcategory, vendor, model, doc_type,
               title, summary, confidence, needs_review,
               created_at, updated_at, extracted_text)
            VALUES (?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?)
            """,
            (
                data["uuid"], data["original_name"], data["stored_path"],
                data.get("mime"), data.get("size"), data.get("sha256"),
                data.get("category"), data.get("subcategory"),
                data.get("vendor"), data.get("model"), data.get("doc_type"),
                data.get("title"), data.get("summary"),
                data.get("confidence", 0), int(data.get("needs_review", 1)),
                now, now, data.get("extracted_text"),
            ),
        )
        doc_id = cur.lastrowid
        for tag in data.get("tags", []) or []:
            attach_tag(c, doc_id, tag)
        _reindex_fts(c, doc_id)
        return doc_id


def attach_tag(c: sqlite3.Connection, doc_id: int, tag: str) -> None:
    tag = tag.strip()
    if not tag:
        return
    c.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
    row = c.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()
    c.execute(
        "INSERT OR IGNORE INTO document_tags(document_id, tag_id) VALUES (?, ?)",
        (doc_id, row["id"]),
    )


def replace_tags(doc_id: int, tags: Iterable[str]) -> None:
    with tx() as c:
        c.execute("DELETE FROM document_tags WHERE document_id=?", (doc_id,))
        for t in tags:
            attach_tag(c, doc_id, t)
        _reindex_fts(c, doc_id)


def get_tags(doc_id: int) -> list[str]:
    rows = conn().execute(
        "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id=t.id "
        "WHERE dt.document_id=? ORDER BY t.name",
        (doc_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["needs_review"] = bool(d.get("needs_review"))
    return d


def list_documents(
    category: str | None = None,
    subcategory: str | None = None,
    vendor: str | None = None,
    model: str | None = None,
    needs_review: bool | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, uuid, original_name, stored_path, mime, size, "
        "category, subcategory, vendor, model, doc_type, title, summary, "
        "confidence, needs_review, created_at, updated_at "
        "FROM documents WHERE 1=1"
    )
    args: list[Any] = []
    if category is not None:
        sql += " AND IFNULL(category,'') = ?"; args.append(category)
    if subcategory is not None:
        sql += " AND IFNULL(subcategory,'') = ?"; args.append(subcategory)
    if vendor is not None:
        sql += " AND IFNULL(vendor,'') = ?"; args.append(vendor)
    if model is not None:
        sql += " AND IFNULL(model,'') = ?"; args.append(model)
    if needs_review is not None:
        sql += " AND needs_review = ?"; args.append(int(needs_review))
    sql += " ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)
    rows = conn().execute(sql, args).fetchall()
    result = []
    for r in rows:
        d = row_to_dict(r)
        d["tags"] = get_tags(d["id"])
        result.append(d)
    return result


def get_document(doc_id: int) -> dict[str, Any] | None:
    row = conn().execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return None
    d = row_to_dict(row)
    d["tags"] = get_tags(doc_id)
    return d


def update_document(doc_id: int, fields: dict[str, Any]) -> bool:
    allowed = {
        "category", "subcategory", "vendor", "model", "doc_type",
        "title", "summary", "confidence", "needs_review", "stored_path",
    }
    sets = []
    args: list[Any] = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            args.append(int(v) if k == "needs_review" else v)
    if not sets:
        return False
    sets.append("updated_at=?")
    args.append(_now())
    args.append(doc_id)
    with tx() as c:
        c.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id=?", args)
        _reindex_fts(c, doc_id)
    return True


def delete_document(doc_id: int) -> dict[str, Any] | None:
    with tx() as c:
        row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        c.execute("DELETE FROM documents_fts WHERE rowid=?", (doc_id,))
        return row_to_dict(row)


def search_documents(query: str, limit: int = 100) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return list_documents(limit=limit)
    # 把每个非空 token 加 *，做前缀匹配，对中文友好
    tokens = [t for t in q.split() if t]
    if not tokens:
        return []
    fts_q = " ".join(f'"{t}"*' for t in tokens)
    rows = conn().execute(
        """
        SELECT d.id, d.uuid, d.original_name, d.stored_path, d.mime, d.size,
               d.category, d.subcategory, d.vendor, d.model, d.doc_type,
               d.title, d.summary, d.confidence, d.needs_review,
               d.created_at, d.updated_at
        FROM documents_fts f
        JOIN documents d ON d.id = f.rowid
        WHERE documents_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_q, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["tags"] = get_tags(d["id"])
        out.append(d)
    return out


def category_tree() -> dict[str, Any]:
    """返回嵌套字典：{大类: {细类: {厂商: {型号: count}}}}，特殊键 __count 表示该层文档数。"""
    rows = conn().execute(
        "SELECT category, subcategory, vendor, model, COUNT(*) AS n "
        "FROM documents GROUP BY category, subcategory, vendor, model"
    ).fetchall()
    tree: dict[str, Any] = {}
    for r in rows:
        cat = r["category"] or "_unclassified"
        sub = r["subcategory"] or "_other"
        ven = r["vendor"] or "_other"
        mod = r["model"] or "_other"
        n = r["n"]
        tree.setdefault(cat, {"__count": 0, "children": {}})
        tree[cat]["__count"] += n
        tree[cat]["children"].setdefault(sub, {"__count": 0, "children": {}})
        tree[cat]["children"][sub]["__count"] += n
        tree[cat]["children"][sub]["children"].setdefault(ven, {"__count": 0, "children": {}})
        tree[cat]["children"][sub]["children"][ven]["__count"] += n
        tree[cat]["children"][sub]["children"][ven]["children"].setdefault(mod, 0)
        tree[cat]["children"][sub]["children"][ven]["children"][mod] += n
    return tree
