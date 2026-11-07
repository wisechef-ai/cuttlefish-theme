"""Unit: cuttlefish.hooks — observers that never raise and never leak text.

The contract files pin the producer-faithful flows; these pin the hostile edges
odd types, unhashable payloads, repeated opens and the fallbacks.
"""

from __future__ import annotations

import hashlib
import importlib

import pytest

SID = "20261105_101500_ab12cd"
SK = "agent:main:desktop:dm:" + SID


@pytest.fixture
def sent():
    from cuttlefish_theme import cuttlefish  # noqa: F401 - bind the package first
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    got: list[tuple[str, dict]] = []
    events.set_broadcaster(lambda _pid, event, payload=None: got.append((event, dict(payload or {}))))
    yield got
    events.set_broadcaster(None)


def hooks():
    from cuttlefish_theme import cuttlefish  # noqa: F401
    return importlib.import_module("cuttlefish_theme.cuttlefish.hooks")


APPROVAL = dict(command="rm -rf /tmp/secret", description="d", pattern_key="rm_rf", pattern_keys=["rm_rf"],
                session_key=SK, surface="gateway", turn_id="t1", tool_call_id="c1", session_id=SID)


def test_repeated_opens_are_idempotent_on_the_wire(sent):
    h = hooks()
    h.pre_approval_request(**APPROVAL)
    h.pre_approval_request(**APPROVAL)
    ids = [p["request_id"] for e, p in sent if e == "needs_you"]
    assert len(ids) == 2 and ids[0] == ids[1], "the same request must keep the same key"


def test_odd_types_never_raise_and_never_emit(sent):
    h = hooks()
    h.on_human_input_request(kind=["approval"], request_id={"x": 1}, session_id=SID, session_key=SK,
                             prompt="secret", platform=None)
    h.pre_approval_request(**{**APPROVAL, "pattern_key": ["un", "hashable"], "turn_id": None, "surface": 7})
    h.post_approval_response(**{**APPROVAL, "session_id": SID, "choice": ["once"]})
    h.api_request_error(session_id=[SID], retryable=False)
    h.api_request_error(session_id=SID, retryable=0)
    h.api_request_error(session_id=SID, retryable="false")
    h.on_human_input_resolved()
    assert [e for e, _ in sent if e == "error"] == [], "unattributable errors are not news"
    for _, p in sent:
        assert "secret" not in repr(p)


def test_derived_key_ignores_unstable_fields_but_keeps_the_five(sent):
    h = hooks()
    h.pre_approval_request(**APPROVAL)
    first = sent[-1][1]["request_id"]
    h.pre_approval_request(**{**APPROVAL, "command": "other", "choice": "x", "request_digest": "zz",
                              "pattern_keys": ["a", "b"], "timeout_s": 9})
    assert sent[-1][1]["request_id"] == first
    h.pre_approval_request(**{**APPROVAL, "surface": "cli"})
    assert sent[-1][1]["request_id"] != first


@pytest.mark.parametrize("rid", ["", 0, 7, {"id": 1}, ["r"]])
def test_a_request_id_that_is_not_a_nonempty_string_is_derived_not_trusted(sent, rid):
    """Only the producer's own non-empty string id is passed through; anything
    else (empty, non-string) falls back to the stable derived key."""
    h = hooks()
    h.pre_approval_request(**{**APPROVAL, "request_id": rid})
    assert sent[-1][1]["request_id"].startswith("cf-")
    expected = "cf-" + hashlib.sha256("\x1f".join(
        (SK, "t1", "c1", "rm_rf", "gateway")).encode()).hexdigest()
    assert sent[-1][1]["request_id"] == expected


def test_non_string_session_ids_are_not_attributable(sent):
    h = hooks()
    h.on_human_input_request(kind="approval", request_id="r", session_id=42, session_key=SK)
    h.pre_approval_request(**{**APPROVAL, "session_id": None})
    assert sent == []


def test_error_payload_is_exactly_three_safe_fields(sent):
    h = hooks()
    h.api_request_error(session_id=SID, session_key=SK, retryable=False, reason="sk-SECRET",
                        error={"message": "sk-SECRET"}, base_url="http://x")
    assert [e for e, _ in sent] == ["error"]
    assert sent[0][1] == {"session_id": SID, "session_key": SK, "retryable": False}


def test_human_input_missing_kind_defaults_to_approval(sent):
    h = hooks()
    h.on_human_input_request(request_id="r9", session_id=SID, session_key=SK, prompt="p")
    assert sent[-1][1]["kind"] == "approval"
