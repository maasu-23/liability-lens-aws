"""ui_events: the web page gets text chunks plus tool inputs and results, nothing else."""

import json

from liability_lens.ui_events import to_ui


def test_text_and_tool_start():
    names = {}
    assert to_ui({"event": {"contentBlockDelta": {"delta": {"text": "Hi"}}}}, names) == [{"t": "text", "v": "Hi"}]
    start = {"event": {"contentBlockStart": {"start": {"toolUse": {"name": "case___classify_case", "toolUseId": "a"}}}}}
    assert to_ui(start, names) == [{"t": "tool_start", "name": "classify_case"}]


def test_tool_use_then_result_are_paired_by_id():
    names = {}
    use = {"message": {"role": "assistant", "content": [
        {"text": "Let me check."},
        {"toolUse": {"toolUseId": "x1", "name": "case___compute_entitlement", "input": {"transactions": []}}}]}}
    assert to_ui(use, names) == [{"t": "tool_use", "name": "compute_entitlement", "input": {"transactions": []}}]
    result = {"message": {"role": "user", "content": [
        {"toolResult": {"toolUseId": "x1", "status": "success", "content": [{"text": json.dumps({"ok": 1})}]}}]}}
    assert to_ui(result, names) == [{"t": "tool_result", "name": "compute_entitlement", "data": {"ok": 1}}]


def test_json_blocks_and_unreadable_results():
    names = {"y": "deadline_calendar"}
    msg = {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "y", "content": [{"json": {"a": 2}}]}}]}}
    assert to_ui(msg, names)[0]["data"] == {"a": 2}
    msg = {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "y", "content": [{"text": "oops"}]}}]}}
    assert "error" in to_ui(msg, names)[0]["data"]


def test_other_events_are_dropped():
    names = {}
    for e in (None, "x", {"event": {"messageStop": {}}}, {"init_event_loop": True}, {"message": {"role": "assistant",
              "content": [{"text": "done"}]}}):
        assert to_ui(e, names) == []
