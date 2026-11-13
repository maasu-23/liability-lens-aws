"""Gateway Lambda for the case tools. Dispatches to liability_lens.tools; no logic lives here.

The Gateway passes the tool arguments as the event and the tool name, prefixed with the target
name (`<target>___<tool>`), in the Lambda client context.
"""

import logging

from liability_lens.tools import TOOLS

log = logging.getLogger()
log.setLevel(logging.INFO)


def _tool_name(context) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    return custom.get("bedrockAgentCoreToolName", "").split("___", 1)[-1]


def handler(event, context):
    name = _tool_name(context)
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool {name!r}; available: {', '.join(sorted(TOOLS))}"}
    # Log the tool name and argument keys only: case facts are personal data.
    log.info("tool=%s keys=%s", name, sorted(event or {}))
    try:
        return tool(event or {})
    except Exception:  # never leak a stack trace to the model or the user
        log.exception("tool %s failed", name)
        return {"error": f"{name} failed unexpectedly; please try again or check the inputs"}
