"""Gateway Lambda handler: tool-name routing and error containment."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "tools"))
import handler  # noqa: E402

from test_tools import SUNITA  # noqa: E402


def ctx(tool_name):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": tool_name}))


def test_routes_prefixed_tool_name():
    out = handler.handler(SUNITA, ctx("case___compute_entitlement"))
    assert out["new_regime"]["amount"] == 25_000


def test_unknown_tool():
    assert "unknown tool" in handler.handler({}, ctx("case___delete_everything"))["error"]


def test_missing_client_context():
    assert "unknown tool" in handler.handler({}, SimpleNamespace(client_context=None))["error"]


def test_unexpected_exception_is_contained(monkeypatch):
    def boom(case):
        raise RuntimeError("secret internals")
    monkeypatch.setitem(handler.TOOLS, "classify_case", boom)
    out = handler.handler(SUNITA, ctx("case___classify_case"))
    assert out == {"error": "classify_case failed unexpectedly; please try again or check the inputs"}
