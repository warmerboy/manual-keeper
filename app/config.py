"""配置加载：从 config.json 读取，缺则生成模板。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "anthropic_api_key": "",
    "anthropic_base_url": "",
    "model": "claude-haiku-4-5",
    "port": 8765,
    "storage_dir": "./storage",
    "db_path": "./data/app.db",
    "min_confidence": 0.6,
    "tesseract_cmd": "",
    "cos_secret_id": "",
    "cos_secret_key": "",
    "cos_region": "",
    "cos_bucket": "",
    "share_password": "",
}

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[config] 已生成模板：{CONFIG_PATH}，请填入 anthropic_api_key 后重启")
        return dict(DEFAULT_CONFIG)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    merged = {**DEFAULT_CONFIG, **data}
    return merged


CONFIG = load_config()


def storage_root() -> Path:
    p = Path(CONFIG["storage_dir"])
    if not p.is_absolute():
        p = ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    (p / "files").mkdir(exist_ok=True)
    # v2: 用『待归档』替代旧的 _unclassified
    (p / "files" / "待归档").mkdir(exist_ok=True)
    return p


def db_path() -> Path:
    p = Path(CONFIG["db_path"])
    if not p.is_absolute():
        p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
