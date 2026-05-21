"""
Tool Calling Support for Web Models via Prompt Injection

Based on openclaw-zero-token implementation with enhancements:
- Fenced: ```tool_json\n{"tool":"...","parameters":{...}}\n```
- Bare JSON: {"tool":"...","parameters":{...}}
- XML: <tool_call...</tool_call)> (DeepSeek compat)
- Fuzzy repair for truncated JSON from SSE streams
- Keyword-based conditional injection to reduce ban risk
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

TOOL_EXAMPLE = """Example: to add 1 to number 5, return:
```tool_json
{"tool":"plus_one","parameters":{"number":"5"}}
```
(plus_one is just an example, not a real tool)"""

EN_TEMPLATE = """Tools: {tool_defs}

{example}

Your actual tools are listed above. To use one, reply ONLY with the tool_json block.
No tool needed? Answer directly.

"""

EN_STRICT_TEMPLATE = """Tools: {tool_defs}

{example}

Your actual tools are listed above. To use one, reply ONLY with the tool_json block. No extra text.
No tool needed? Answer directly.

"""

CN_TEMPLATE = """工具: {tool_defs}

示例: 要给数字5加1，返回:
```tool_json
{{"tool":"plus_one","parameters":{{"number":"5"}}}}
```
(plus_one仅为示例，非真实工具)

你的真实工具见上方列表。需要时只回复tool_json块。不需要则直接回答。

"""

EXCLUDED_MODELS: Set[str] = {"perplexity-web", "doubao-web"}

STRICT_MODELS: Set[str] = {"chatgpt-web"}

CN_MODELS: Set[str] = {
    "deepseek-web",
    "doubao-web",
    "qwen-cn-web",
    "kimi-web",
    "glm-web",
    "xiaomimo-web",
}

INJECTION_KEYWORDS = [
    "文件", "file", "read", "write", "创建", "写入", "读取", "打开", "保存",
    "桌面", "desktop", "目录", "directory", "folder", "文件夹",
    "执行", "运行", "命令", "command", "run", "exec", "terminal", "终端", "shell",
    "搜索", "search", "查找", "查询", "fetch", "抓取", "网页", "url", "http",
    "天气", "weather", "新闻", "news",
    "发送", "send", "消息", "message", "通知", "notify",
    "帮我", "help me", "查看", "check", "look", "看看", "show",
    "下载", "download", "安装", "install", "更新", "update",
]


def should_inject_tool_prompt(api_id: str) -> bool:
    """Check if tool prompt should be injected for a given API."""
    return api_id not in EXCLUDED_MODELS


def needs_tool_injection(message: str) -> bool:
    """Check if message contains keywords suggesting tool use.
    Only inject tool prompt when keywords match, keeping normal chat
    messages short to reduce ban risk.
    """
    lower = message.lower()
    return any(kw in lower for kw in INJECTION_KEYWORDS)


def get_tool_prompt(api_id: str, tool_definitions: List[Dict]) -> str:
    """Get the appropriate tool prompt template for an API."""
    if api_id in STRICT_MODELS:
        template = EN_STRICT_TEMPLATE
    elif api_id in CN_MODELS:
        template = CN_TEMPLATE
    else:
        template = EN_TEMPLATE

    tool_defs_str = _format_tool_definitions(tool_definitions)
    return template.format(tool_defs=tool_defs_str, example=TOOL_EXAMPLE)


def format_tool_result(tool_name: str, result: str) -> str:
    """Format tool result for feedback to the model."""
    return f"Tool {tool_name} returned: {result}\nPlease continue answering based on this result."


def parse_tool_call(response_text: str) -> Optional[Dict]:
    """Parse a tool call from model response.

    Supports three formats (tried in order):
    1. Fenced: ```tool_json\\n{"tool":"...","parameters":{...}}\\n```
    2. Bare JSON: {"tool":"...","parameters":{...}}
    3. XML: <tool_call..."name":"...","arguments":{...}></tool_call)>
    4. Fuzzy repair: auto-fix truncated JSON from SSE streams
    """
    result = _try_fenced_format(response_text)
    if result:
        return result

    result = _try_bare_json_format(response_text)
    if result:
        return result

    result = _try_xml_format(response_text)
    if result:
        return result

    result = _try_fuzzy_repair(response_text)
    if result:
        return result

    return None


def _try_fenced_format(text: str) -> Optional[Dict]:
    """Try fenced code block format (most reliable)."""
    pattern = r'```tool_json\s*\n?\s*(\{[\s\S]*?)\}?\s*\n?\s*```'
    match = re.search(pattern, text)
    if match:
        return _parse_and_repair(match.group(1))
    return None


def _try_bare_json_format(text: str) -> Optional[Dict]:
    """Try bare JSON format without fences."""
    pattern = r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*(\{[\s\S]*?\})\s*\}'
    match = re.search(pattern, text)
    if match:
        try:
            params = json.loads(match.group(2))
            return {"tool": match.group(1), "parameters": params}
        except json.JSONDecodeError:
            return None
    return None


def _try_xml_format(text: str) -> Optional[Dict]:
    """Try XML tool_call format (DeepSeek compatibility)."""
    pattern = r'<tool_call[^>]*>([\s\S]*?)<\/tool_call>'
    match = re.search(pattern, text)
    if match:
        return _parse_and_repair(match.group(1))
    return None


def _try_fuzzy_repair(text: str) -> Optional[Dict]:
    """Fuzzy repair for truncated JSON from SSE streams.

    Common issue: SSE stream drops the final }
    e.g. {"tool":"exec","parameters":{"command":"ls"
    """
    pattern = r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*\{(.*)'
    match = re.search(pattern, text)
    if match:
        repaired = f'{{"tool":"{match.group(1)}","parameters":{{{match.group(2)}}}}}'
        return _parse_and_repair(repaired)
    return None


def _parse_and_repair(raw: str) -> Optional[Dict]:
    """Parse JSON with auto-repair for unbalanced braces and common SSE truncation issues."""
    try:
        cleaned = raw.strip()

        if not cleaned:
            return None

        opens = cleaned.count("{")
        closes = cleaned.count("}")
        if opens > closes:
            cleaned += "}" * (opens - closes)

        quotes = cleaned.count('"')
        if quotes % 2 != 0:
            cleaned += '"'

        obj = json.loads(cleaned)
        if "tool" in obj and isinstance(obj["tool"], str):
            return {
                "tool": obj["tool"],
                "parameters": obj.get("parameters", {}),
            }
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse tool call JSON: {e}")

    return None


def _format_tool_definitions(tools: List[Dict]) -> str:
    """Format tool definitions for prompt injection."""
    if not tools:
        return "No tools available."

    defs = []
    for tool in tools:
        name = tool.get("name", "unknown")
        description = tool.get("description", "No description")
        params = tool.get("parameters", {})

        param_str = ""
        if params.get("properties"):
            param_list = []
            for prop_name, prop_info in params["properties"].items():
                param_type = prop_info.get("type", "string")
                desc = prop_info.get("description", "")
                param_list.append(f"  - {prop_name} ({param_type}): {desc}")
            param_str = "\n  Parameters:\n" + "\n".join(param_list)

        defs.append(f"- **{name}**: {description}{param_str}")

    return "\n".join(defs)
