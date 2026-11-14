"""Turn the agent's stream into small events for the web page.

The page shows two things: the model's words as they stream, and a case file built only from tool
inputs and results. So each Strands event becomes at most a few of these:

    {"t": "text", "v": "..."}                         a chunk of the reply
    {"t": "tool_start", "name": "classify_case"}       a tool call began (for the progress line)
    {"t": "tool_use", "name": ..., "input": {...}}     the facts the model passed to a tool
    {"t": "tool_result", "name": ..., "data": {...}}   what the tool returned

Tool names arrive from the Gateway as "<target>___<tool>"; the page only sees the tool name.
"""

from __future__ import annotations

import json


def _short(name: str) -> str:
    return name.split("___", 1)[-1]


def _result_data(content: list) -> dict:
    for block in content or []:
        if isinstance(block.get("json"), dict):
            return block["json"]
        if isinstance(block.get("text"), str):
            try:
                value = json.loads(block["text"])
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return {"error": "the tool returned no readable result"}


def to_ui(event, names: dict[str, str]) -> list[dict]:
    """Convert one Strands stream event. `names` maps toolUseId -> tool name across the turn."""
    if not isinstance(event, dict):
        return []
    inner = event.get("event")
    if isinstance(inner, dict):
        delta = (inner.get("contentBlockDelta") or {}).get("delta") or {}
        if isinstance(delta.get("text"), str) and delta["text"]:
            return [{"t": "text", "v": delta["text"]}]
        tool = ((inner.get("contentBlockStart") or {}).get("start") or {}).get("toolUse")
        if tool and tool.get("name"):
            return [{"t": "tool_start", "name": _short(tool["name"])}]
        return []
    message = event.get("message")
    if not isinstance(message, dict):
        return []
    out = []
    for block in message.get("content") or []:
        use = block.get("toolUse")
        if use and message.get("role") == "assistant":
            names[use.get("toolUseId", "")] = _short(use.get("name", ""))
            out.append({"t": "tool_use", "name": _short(use.get("name", "")), "input": use.get("input") or {}})
        result = block.get("toolResult")
        if result:
            out.append({"t": "tool_result", "name": names.get(result.get("toolUseId", ""), ""),
                        "data": _result_data(result.get("content"))})
    return out
