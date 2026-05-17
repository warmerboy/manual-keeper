"""调用 Claude API 自动识别文档元数据；缺 key / 缺文本时优雅降级。"""
from __future__ import annotations

import json
from typing import Any

from ..config import CONFIG

SYSTEM_PROMPT = """你是一个个人技术资料管理助手。用户上传的文档可能是：
- 设备说明书（电气、机械、仪表、家电、网络设备等）
- 软件使用文档（操作指南、教程、API 手册）
- 政策法规 / 管理规定 / 标准规范
- 生活类规定（社区规则、操作流程、注意事项）

你的任务是阅读文档片段（标题、首页、目录、章节摘录），识别它的归类信息并调用 classify 工具返回结构化结果。

字段填写要求：
- category（大类）：用中文短语，例如「电气设备」「机械设备」「软件文档」「政策法规」「生活规定」「网络设备」「仪表仪器」「家用电器」等。
- subcategory（细类）：在大类下进一步细分，例如电气设备下分「PLC」「变频器」「断路器」；软件文档下分「办公软件」「开发工具」；政策法规下分「行业标准」「管理办法」。
- vendor（厂商/发布方）：若是设备/软件填厂商；若是政策填发布机构；若无可填 null。
- model（型号/版本/编号）：设备型号、软件版本、政策文号；无可填 null。
- doc_type（文档类型）：例如「用户手册」「安装指南」「技术规格」「操作教程」「管理办法」「行业标准」「注意事项」。
- title：清晰的中文标题，避免乱码。
- summary：1-3 句话，概括这份资料讲什么，对什么场景有用。
- tags：3-8 个对将来检索有帮助的关键词（设备名、功能词、应用场景等），用中文。
- confidence：0-1 之间，反映你对识别准确性的信心。文档片段过短、内容看不出来时降到 0.4 以下。

严格仅通过 classify 工具返回，不要输出额外文字。
"""

CLASSIFY_TOOL = {
    "name": "classify",
    "description": "返回该文档的结构化分类与摘要。",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "一级大类，中文短语"},
            "subcategory": {"type": ["string", "null"], "description": "二级细类，中文短语；不确定填 null"},
            "vendor": {"type": ["string", "null"], "description": "厂商/发布方；无填 null"},
            "model": {"type": ["string", "null"], "description": "型号/版本/编号；无填 null"},
            "doc_type": {"type": ["string", "null"], "description": "文档类型，例如『用户手册』"},
            "title": {"type": "string", "description": "清晰的中文标题"},
            "summary": {"type": "string", "description": "1-3 句中文摘要"},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 8,
                "description": "3-8 个中文关键词标签"
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["category", "title", "summary", "tags", "confidence"]
    },
}


def _empty_result() -> dict[str, Any]:
    return {
        "category": None, "subcategory": None, "vendor": None, "model": None,
        "doc_type": None, "title": None, "summary": None, "tags": [],
        "confidence": 0.0,
    }


def classify_text(text: str, original_name: str) -> dict[str, Any]:
    """根据抽取的文本调用 Claude；任何失败都返回空结果（不抛异常）。"""
    api_key = (CONFIG.get("anthropic_api_key") or "").strip()
    if not api_key:
        return _empty_result()
    if not text or len(text.strip()) < 20:
        # 文本太少：仍可让 Claude 仅根据文件名猜，但传 file_name 帮助
        snippet = f"[文档抽取文本几乎为空，仅有文件名供参考]\n文件名：{original_name}"
    else:
        snippet = f"文件名：{original_name}\n\n--- 文档内容（已截断）---\n{text[:6000]}"

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CONFIG.get("model", "claude-haiku-4-5"),
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify"},
            messages=[{"role": "user", "content": snippet}],
        )
    except Exception as e:
        print(f"[classify] Claude API 调用失败：{e}")
        return _empty_result()

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "classify":
            data = block.input or {}
            # 容错：如果模型把 JSON 编码成字符串
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            result = _empty_result()
            for k in result:
                if k in data and data[k] is not None:
                    result[k] = data[k]
            # tags 必须是 list[str]
            if not isinstance(result["tags"], list):
                result["tags"] = []
            result["tags"] = [str(t).strip() for t in result["tags"] if str(t).strip()]
            try:
                result["confidence"] = float(result.get("confidence") or 0.0)
            except Exception:
                result["confidence"] = 0.0
            return result
    return _empty_result()
