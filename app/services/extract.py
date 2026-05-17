"""文本抽取：按扩展名分发到 PDF / docx / 图片 / HTML / markdown / 文本。"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from . import ocr

MAX_CHARS = 12000  # 单文档最多保留的抽取文本长度，避免 DB / API 撑爆


def _read_text(path: Path, encoding: str = "utf-8") -> str:
    for enc in (encoding, "utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = reader.pages
        # 取前 5 页 + 末页（若超过 5 页）
        idxs = list(range(min(5, len(pages))))
        if len(pages) > 5:
            idxs.append(len(pages) - 1)
        parts = []
        for i in idxs:
            try:
                parts.append(pages[i].extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception as e:
        return f"[PDF 解析失败: {e}]"


def extract_docx(path: Path) -> str:
    try:
        import docx
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs if p.text)
    except Exception as e:
        return f"[docx 解析失败: {e}]"


def extract_html(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(_read_text(path), "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)
    except Exception as e:
        return f"[HTML 解析失败: {e}]"


def extract_image(path: Path) -> Tuple[str, bool]:
    """返回 (文本, ocr_是否可用)。"""
    text = ocr.ocr_image(path)
    return text, ocr.available()


def extract(path: Path) -> dict:
    """统一入口，返回 {text, ocr_available, type}。"""
    ext = path.suffix.lower()
    ocr_available = True  # 仅对图片类型有意义
    if ext == ".pdf":
        text = extract_pdf(path); kind = "pdf"
    elif ext in (".docx", ".doc"):
        # .doc 旧格式 python-docx 不支持，提示用户转格式
        if ext == ".doc":
            text = "[.doc 旧格式不支持解析，请另存为 .docx]"
        else:
            text = extract_docx(path)
        kind = "word"
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"):
        text, ocr_available = extract_image(path)
        kind = "image"
    elif ext in (".html", ".htm"):
        text = extract_html(path); kind = "html"
    elif ext in (".md", ".markdown"):
        text = _read_text(path); kind = "markdown"
    elif ext in (".txt", ".log", ".csv", ".tsv"):
        text = _read_text(path); kind = "text"
    else:
        text = _read_text(path); kind = "other"

    if text and len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...[已截断]"
    return {"text": text or "", "ocr_available": ocr_available, "type": kind}
