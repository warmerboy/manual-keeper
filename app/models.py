"""Pydantic 模型：请求/响应体。"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class DocumentUpdate(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    vendor: str | None = None
    model: str | None = None
    doc_type: str | None = None
    title: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    needs_review: bool | None = None


class ClassifyResult(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    vendor: str | None = None
    model: str | None = None
    doc_type: str | None = None
    title: str | None = None
    summary: str | None = None
    tags: list[str] = []
    confidence: float = 0.0


class DocumentOut(BaseModel):
    id: int
    uuid: str
    original_name: str
    stored_path: str
    mime: str | None = None
    size: int | None = None
    category: str | None = None
    subcategory: str | None = None
    vendor: str | None = None
    model: str | None = None
    doc_type: str | None = None
    title: str | None = None
    summary: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    created_at: str
    updated_at: str
    tags: list[str] = []
