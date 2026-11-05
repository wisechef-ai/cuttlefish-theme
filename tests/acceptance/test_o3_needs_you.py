"""ACCEPTANCE CONTRACT — O3 (Python half): "needs you" and errors reach the desktop through broadcast_plugin_event (locked).

Hook kwargs below are copied from the PRODUCERS at v0.22.7: tools/human_input_hooks.py (human_input_request payload),
tools/approval_gateway_wait.py (pre_approval_request/post_approval_response), agent/api_request_hooks.py
(api_request_error). Ceiling ↔ floor: hooks never raise and never leak prompt/command text AND every request/resolve
pair produces exactly the event the desktop reducer consumes (contract/README.md "Feed inputs").
"""
from __future__ import annotations

import importlib

import pytest

from .helpers import FakeCtx, plugin_package

WIRE = "plugin.cuttlefish-theme."


@pytest.fixture
def sent():
    plugin_package()
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    got: list[tuple[str, str, dict]] = []
    events.set_broadcaster(lambda plugin_id, event, payload=None: got.append((plugin_id, event, dict(payload or {}))))
    yield got
    events.set_broadcaster(None)


def hooks():
    plugin_package()
    return importlib.import_module("cuttlefish_theme.cuttlefish.hooks")


HUMAN = dict(kind="approval", request_id="9f1c", session_id="20261105_101500_ab12cd", session_key="20261105_101500_ab12cd",
             platform="desktop", prompt="rm -rf /tmp/secret-thing")
APPROVAL = dict(command="rm -rf /tmp/secret-thing", description="recursive delete", pattern_key="rm_rf",
                session_key="20261105_101500_ab12cd", turn_id="t1", tool_call_id="c1", session_id="20261105_101500_ab12cd")


def test_O3_1_wire_name_and_plugin_id(sent):
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    assert events.EVENT_PREFIX == WIRE
    hooks().on_human_input_request(**HUMAN)
    assert sent and sent[0][0] == "cuttlefish-theme" and sent[0][1] == "needs_you"


def test_O3_2_human_input_request_and_resolve_toggle_needs_you(sent):
    h = hooks()
    h.on_human_input_request(**HUMAN)
    h.on_human_input_resolved(**HUMAN, outcome="approved")
    assert [(e, p["active"]) for _, e, p in sent] == [("needs_you", True), ("needs_you", False)]
    for _, _, p in sent:
        assert p["session_id"] == HUMAN["session_id"] and p["session_key"] == HUMAN["session_key"]
        assert p["request_id"] == "9f1c" and p["kind"] == "approval"


def test_O3_3_clarify_counts_too(sent):
    hooks().on_human_input_request(**{**HUMAN, "kind": "clarify", "request_id": "c7"})
    assert sent[-1][1:] and sent[-1][2]["kind"] == "clarify" and sent[-1][2]["active"] is True


def test_O3_4_approval_hooks_are_handled_without_double_counting(sent):
    h = hooks()
    h.on_human_input_request(**HUMAN)
    h.pre_approval_request(**APPROVAL)
    h.post_approval_response(**APPROVAL, choice="deny")
    h.on_human_input_resolved(**HUMAN, outcome="denied")
    actives = [p["active"] for _, e, p in sent if e == "needs_you"]
    assert actives[0] is True and actives[-1] is False
    # the desktop keys requests by request_id; an approval-only pair (no human_input wrapper) still opens AND closes
    sent.clear()
    h.pre_approval_request(**APPROVAL)
    h.post_approval_response(**APPROVAL, choice="once")
    seq = [(e, p["active"]) for _, e, p in sent if e == "needs_you"]
    assert seq and seq[0][1] is True and seq[-1][1] is False, seq
    assert len({p["request_id"] for _, e, p in sent if e == "needs_you"}) == 1, "open and close name the same request"


def test_O3_5_payloads_never_carry_prompt_or_command_text(sent):
    h = hooks()
    h.on_human_input_request(**HUMAN)
    h.pre_approval_request(**APPROVAL)
    blob = repr(sent)
    assert "secret-thing" not in blob and "recursive delete" not in blob, blob


def test_O3_6_only_a_non_retryable_api_error_is_an_error(sent):
    h = hooks()
    base = dict(task_id="t", turn_id="t1", api_request_id="a1", session_id="S1", platform="desktop", model="m",
                provider="p", base_url="http://x", api_mode="chat_completions", api_call_count=1, api_duration=0.1,
                started_at=0.0, ended_at=0.1, status_code=401, retry_count=0, max_retries=3, reason="auth",
                error={"type": "AuthenticationError", "message": "bad key sk-SECRET"}, request={})
    h.api_request_error(**{**base, "retryable": True})
    h.api_request_error(**{**base, "retryable": None})
    assert sent == [], "retryable / unknown errors are not news (the turn may still succeed)"
    h.api_request_error(**{**base, "retryable": False})
    assert [e for _, e, _ in sent] == ["error"]
    p = sent[0][2]
    assert p["session_id"] == "S1" and p["retryable"] is False
    assert "SECRET" not in repr(sent), "error text is never broadcast"


def test_O3_7_hooks_never_raise_even_when_broadcast_fails_or_kwargs_are_odd():
    plugin_package()
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    h = hooks()

    def boom(*_a, **_k):
        raise RuntimeError("gateway gone")

    events.set_broadcaster(boom)
    try:
        h.on_human_input_request(**HUMAN)
        h.on_human_input_resolved(**HUMAN, outcome="error")
        h.pre_approval_request(**APPROVAL)
        h.post_approval_response(**APPROVAL, choice="deny")
        h.api_request_error(session_id="S", retryable=False)
        h.on_human_input_request()  # no kwargs at all
        h.on_human_input_request(session_id=None, request_id=None, kind=None, unexpected=object())
    finally:
        events.set_broadcaster(None)


def test_O3_8_no_session_no_event(sent):
    hooks().on_human_input_request(kind="approval", request_id="x", session_id="", session_key="", platform="cli")
    assert sent == [], "an event the desktop cannot attribute to a session is not sent"


def test_O3_9_register_wires_these_callbacks():
    ctx = FakeCtx()
    plugin_package().register(ctx)
    h = hooks()
    for name in ("pre_approval_request", "post_approval_response", "on_human_input_request", "on_human_input_resolved",
                 "api_request_error"):
        assert ctx.hooks.get(name) == [getattr(h, name)], name


def test_O3_10_default_broadcaster_is_the_public_core_door_imported_lazily():
    plugin_package()
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    src = (events.__file__ and open(events.__file__).read()) or ""
    assert "hermes_cli.plugin_events" in src and "broadcast_plugin_event" in src
    events.set_broadcaster(None)
    # with no Hermes on the path (this test venv) a send is a silent no-op, never an ImportError
    events.emit("needs_you", {"session_id": "S", "session_key": "S", "request_id": "r", "kind": "approval", "active": True})
