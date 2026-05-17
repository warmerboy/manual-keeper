"""调用 Claude API 自动识别文档元数据。

v2 收敛策略：
- 大类锁死 5 个枚举（tool_use enum 协议层强制）
- 把当前数据库里已用过的细类喂给 AI，引导它复用而非创造
- 厂商 / 型号 / 文档类型作为元数据抽取，不参与目录
"""
from __future__ import annotations

import json
from typing import Any

from ..config import CONFIG
from . import taxonomy


def _build_system_prompt(known_subcategories: dict[str, list[str]]) -> str:
    """根据当前已有的细类拼系统提示词，引导 AI 收敛。"""
    active = taxonomy.get_active_categories()
    lines = [
        "你是一个个人技术资料管理助手，负责识别用户上传文档的归类信息。",
        "",
        f"## 第一层大类（严格在以下 {len(active)} 个中选 1 个，不可创造新大类）：",
    ]
    # 兼容默认 5 个的描述；其他大类只给名字
    desc_map = {
        "说明书": "设备、产品的使用手册 / 安装指南 / 技术规格",
        "软件文档": "软件的用法 / 教程 / API 手册 / 开发文档",
        "电子书": "小说、教材、工具书、漫画、杂志期刊、学术论文",
        "规章制度": "国家法律、行政法规、行业标准、公司规章、管理办法",
        "待归档": "实在判断不出归属、或文档内容过于模糊（同时把 confidence 设到 0.4 以下）",
    }
    for cat in active:
        desc = desc_map.get(cat, "")
        if desc:
            lines.append(f"- **{cat}**：{desc}")
        else:
            lines.append(f"- **{cat}**")
    lines += [
        "",
        "## 第二层细类（subcategory）选择原则：",
        "- **绝对优先：复用下面列出的『已有细类』**。如果新文档能套进现有细类，必须用现有的名字，不要造近义词。",
        "  例如已有「摄影摄像」就不要新建「摄像设备」「拍摄器材」；已有「家用电器」就不要新建「家电」。",
        "- 如果实在找不到合适的已有细类，可以参考下方『建议清单』新建一个，名字要简洁通用。",
        "- 选了大类「待归档」时，subcategory 填 null。",
        "",
        "## 当前数据库里已有的细类（强烈建议复用）：",
    ]
    if known_subcategories:
        for cat in active:
            subs = known_subcategories.get(cat, [])
            if subs:
                lines.append(f"- **{cat}**：{ '、'.join(subs) }")
        if not any(known_subcategories.get(c) for c in active):
            lines.append("（数据库目前为空，可以从建议清单中选）")
    else:
        lines.append("（数据库目前为空，可以从下方建议清单中选）")

    lines += [
        "",
        "## 各大类的细类建议清单（仅在已有细类不合适时参考）：",
    ]
    for cat in active:
        suggested = taxonomy.SUGGESTED_SUBCATEGORIES.get(cat, [])
        if suggested:
            lines.append(f"- **{cat}**：{ '、'.join(suggested) }")

    lines += [
        "",
        "## 其他字段：",
        "- **vendor**（厂商/发布方）：设备/软件填厂商名，政策填发布机构名，电子书填出版社/作者。无可填 null。同一厂商使用一致的名字（如『DJI』而不是『大疆』『大疆创新』『大疆创新科技有限公司』）。",
        "- **model**（型号/版本/编号）：设备型号、软件版本、政策文号。无可填 null。",
        "- **doc_type**（文档类型）：例如『用户手册』『安装指南』『行业标准』『教程』『小说』。",
        "- **title**：清晰的中文标题。",
        "- **summary**：1-3 句话概括文档内容和适用场景（用户能看到）。",
        "- **reorg_summary**：超极简一句话（不超过 50 字），形如『DJI Osmo Mobile 8 手持手机稳定器用户手册』，专门给系统做一键重整使用，要点是能让 AI 一眼看出这是『什么类型的什么东西』。用户看不到。",
        "- **tags**：3-8 个利于检索的关键词。",
        "- **confidence**：0-1，反映识别的把握。文档片段过短或看不出来时降到 0.4 以下。",
        "",
        "严格仅通过 classify 工具返回，不要输出额外文字。",
    ]
    return "\n".join(lines)


def _build_classify_tool() -> dict[str, Any]:
    return {
        "name": "classify",
        "description": "返回该文档的结构化分类与摘要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": taxonomy.get_active_categories(),
                    "description": "一级大类，必须从给定枚举中选 1 个",
                },
                "subcategory": {
                    "type": ["string", "null"],
                    "description": "二级细类。优先复用『已有细类』中的名字。大类为『待归档』时填 null",
                },
                "vendor": {"type": ["string", "null"], "description": "厂商 / 发布方；无填 null"},
                "model": {"type": ["string", "null"], "description": "型号 / 版本 / 编号；无填 null"},
                "doc_type": {"type": ["string", "null"], "description": "文档类型，例如『用户手册』"},
                "title": {"type": "string", "description": "清晰的中文标题"},
                "summary": {"type": "string", "description": "1-3 句中文摘要（用户能看到）"},
                "reorg_summary": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "不超过 50 字的超极简一句话，专供系统重整使用，用户看不到",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 8,
                    "description": "3-8 个中文关键词标签",
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["category", "title", "summary", "reorg_summary", "tags", "confidence"],
        },
    }


def _empty_result() -> dict[str, Any]:
    return {
        "category": None, "subcategory": None, "vendor": None, "model": None,
        "doc_type": None, "title": None, "summary": None, "reorg_summary": None,
        "tags": [], "confidence": 0.0,
    }


def classify_text(
    text: str,
    original_name: str,
    known_subcategories: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """根据抽取的文本调用 Claude；任何失败都返回空结果（不抛异常）。

    known_subcategories: {大类: [已有细类...]}，用于引导 AI 复用现有分类。
    """
    api_key = (CONFIG.get("anthropic_api_key") or "").strip()
    if not api_key:
        return _empty_result()
    if not text or len(text.strip()) < 20:
        snippet = f"[文档抽取文本几乎为空，仅有文件名供参考]\n文件名：{original_name}"
    else:
        snippet = f"文件名：{original_name}\n\n--- 文档内容（已截断）---\n{text[:6000]}"

    system_prompt = _build_system_prompt(known_subcategories or {})
    classify_tool = _build_classify_tool()

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CONFIG.get("model", "claude-haiku-4-5"),
            max_tokens=1024,
            system=system_prompt,
            tools=[classify_tool],
            tool_choice={"type": "tool", "name": "classify"},
            messages=[{"role": "user", "content": snippet}],
        )
    except Exception as e:
        print(f"[classify] Claude API 调用失败：{e}")
        return _empty_result()

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "classify":
            data = block.input or {}
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            result = _empty_result()
            for k in result:
                if k in data and data[k] is not None:
                    result[k] = data[k]
            # 大类兜底：强制收敛到 5 个枚举
            result["category"] = taxonomy.normalize_category(result.get("category"))
            # 待归档下不应有细类
            if result["category"] == taxonomy.UNCLASSIFIED:
                result["subcategory"] = None
            if not isinstance(result["tags"], list):
                result["tags"] = []
            result["tags"] = [str(t).strip() for t in result["tags"] if str(t).strip()]
            try:
                result["confidence"] = float(result.get("confidence") or 0.0)
            except Exception:
                result["confidence"] = 0.0
            return result
    return _empty_result()
