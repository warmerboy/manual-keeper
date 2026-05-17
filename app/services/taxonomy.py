"""分类常量：默认 5 个一级大类（种子枚举）+ 每个大类下的建议细类。

v2 锁死的是 DEFAULT_CATEGORIES；一键重整后大类可以变化，"当前激活的大类清单"
通过 get_active_categories() 从 DB meta.active_categories 读取，缺失时退回到
DEFAULT_CATEGORIES（即首次启动时和 v2 行为一致）。

UNCLASSIFIED（"待归档"）是永远保留的特殊大类，AI 不得改名/删除。
"""
from __future__ import annotations

import json

# 默认大类（首次启动 / DB 没有 active_categories 时使用）
DEFAULT_CATEGORIES: list[str] = [
    "说明书",
    "软件文档",
    "电子书",
    "规章制度",
    "待归档",
]

# 别名（向后兼容旧代码引用 taxonomy.CATEGORIES 的地方）
CATEGORIES = DEFAULT_CATEGORIES

# 待归档是永久兑底大类：不分细类，重整时也不可被改名
UNCLASSIFIED = "待归档"

ACTIVE_CATEGORIES_KEY = "active_categories"

# 每个大类下的建议细类（AI 优先复用此列表 + 数据库已有的细类）
SUGGESTED_SUBCATEGORIES: dict[str, list[str]] = {
    "说明书": [
        "摄影摄像", "音视频", "电脑数码", "手机数码",
        "家用电器", "厨房家电", "个护清洁",
        "工具器材", "户外运动",
        "网络通讯", "工业设备", "仪器仪表",
        "汽车出行", "其他设备",
    ],
    "软件文档": [
        "操作系统", "办公软件", "开发工具", "设计软件",
        "视频音频软件", "游戏", "移动应用",
        "浏览器与网络", "AI 与机器学习", "其他软件",
    ],
    "电子书": [
        "小说", "文学散文", "工具书参考书", "教材教辅",
        "杂志期刊", "漫画绘本", "学术论文", "其他读物",
    ],
    "规章制度": [
        "国家法律", "行政法规", "行业标准", "地方法规",
        "公司规章", "管理办法", "社区与物业", "操作规程", "其他",
    ],
    "待归档": [],
}


def get_active_categories() -> list[str]:
    """读取当前激活的大类清单（DB > DEFAULT）。永远确保 UNCLASSIFIED 在末尾。"""
    # 延迟导入，避免循环 import
    from .. import db
    raw = db.get_meta(ACTIVE_CATEGORIES_KEY)
    if not raw:
        return list(DEFAULT_CATEGORIES)
    try:
        cats = json.loads(raw)
        if not isinstance(cats, list) or not all(isinstance(x, str) for x in cats):
            return list(DEFAULT_CATEGORIES)
    except Exception:
        return list(DEFAULT_CATEGORIES)
    # 确保 待归档 永远存在
    if UNCLASSIFIED not in cats:
        cats.append(UNCLASSIFIED)
    return cats


def set_active_categories(cats: list[str]) -> None:
    """保存新的大类清单。会自动确保 UNCLASSIFIED 存在。"""
    from .. import db
    cats = list(cats)
    if UNCLASSIFIED not in cats:
        cats.append(UNCLASSIFIED)
    db.set_meta(ACTIVE_CATEGORIES_KEY, json.dumps(cats, ensure_ascii=False))


def is_valid_category(name: str | None) -> bool:
    return name in get_active_categories()


def normalize_category(name: str | None) -> str:
    """把任何输入 category 收敛到当前激活清单；不在列表里则归入待归档。"""
    cats = get_active_categories()
    if name in cats:
        return name
    return UNCLASSIFIED
