"""图片 OCR：检测 tesseract 是否可用，否则优雅降级。"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..config import CONFIG

try:
    import pytesseract
    from PIL import Image
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False


def _resolve_tesseract() -> str | None:
    cmd = (CONFIG.get("tesseract_cmd") or "").strip()
    if cmd and Path(cmd).exists():
        return cmd
    found = shutil.which("tesseract")
    return found


def available() -> bool:
    if not _IMPORT_OK:
        return False
    exe = _resolve_tesseract()
    if not exe:
        return False
    try:
        pytesseract.pytesseract.tesseract_cmd = exe
        return True
    except Exception:
        return False


def ocr_image(path: Path) -> str:
    if not available():
        return ""
    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img, lang="chi_sim+eng")
    except Exception:
        # 中文包没装就退化到英文
        try:
            img = Image.open(path)
            return pytesseract.image_to_string(img)
        except Exception:
            return ""
