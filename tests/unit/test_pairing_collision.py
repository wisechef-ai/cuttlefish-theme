"""Unit: F4 — `active:false` only when the LAST open request sharing the slot closes (R-P2).

A pair whose hook shares its derived key with a second, unpaired hook must stay
active until that second one closes too, and the one `false` carries the id of
the one `true`."""

from __future__ import annotations

import importlib

import pytest

K = dict(session_id="s", session_key="SK", turn_id="t", tool_call_id="c", pattern_key="p", surface="gateway")
H = dict(session_id="s", session_key="SK", kind="approval")


@pytest.fixture
def wire():
    from cuttlefish_theme import cuttlefish  # noqa: F401
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    hooks = importlib.import_module("cuttlefish_theme.cuttlefish.hooks")
    got: list[tuple[bool, str]] = []
    events.set_broadcaster(lambda _p, e, pl=None: got.append((pl["active"], pl["request_id"])))
    yield hooks, got
    events.set_broadcaster(None)


def test_F4_human_first_then_two_colliding_hooks(wire):
    h, got = wire
    h.on_human_input_request(request_id="h1", **H)
    h.pre_approval_request(**K)
    h.pre_approval_request(**K)
    assert got == [(True, "h1")]
    h.post_approval_response(**K)
    h.on_human_input_resolved(request_id="h1", **H)
    assert got == [(True, "h1")], "one K is still open: no false yet"
    h.post_approval_response(**K)
    assert got == [(True, "h1"), (False, "h1")]


def test_F4_mirror_two_colliding_hooks_then_the_human(wire):
    h, got = wire
    h.pre_approval_request(**K)
    h.pre_approval_request(**K)
    h.on_human_input_request(request_id="h1", **H)
    assert [a for a, _ in got] == [True]
    rid = got[0][1]
    h.post_approval_response(**K)
    h.on_human_input_resolved(request_id="h1", **H)
    assert [a for a, _ in got] == [True], "one K is still open: no false yet"
    h.post_approval_response(**K)
    assert got == [(True, rid), (False, rid)]


def test_F4_both_hooks_close_while_the_human_is_still_open(wire):
    h, got = wire
    h.on_human_input_request(request_id="h1", **H)
    h.pre_approval_request(**K)
    h.pre_approval_request(**K)
    h.post_approval_response(**K)
    h.post_approval_response(**K)
    assert got == [(True, "h1")], "the human question is still open"
    h.on_human_input_resolved(request_id="h1", **H)
    assert got == [(True, "h1"), (False, "h1")]


def test_F4_stray_close_after_everything_closed_emits_nothing(wire):
    h, got = wire
    h.on_human_input_request(request_id="h1", **H)
    h.pre_approval_request(**K)
    h.post_approval_response(**K)
    h.on_human_input_resolved(request_id="h1", **H)
    h.post_approval_response(**K)
    assert got == [(True, "h1"), (False, "h1")]


def test_F4_a_colliding_hook_stays_pairable_with_a_second_human(wire):
    """Two colliding hooks and two humans are ONE question: one true, one false after the last close."""
    h, got = wire
    h.pre_approval_request(**K)
    h.pre_approval_request(**K)
    h.on_human_input_request(request_id="h1", **H)
    h.on_human_input_request(request_id="h2", **H)
    assert [a for a, _ in got] == [True]
    h.post_approval_response(**K)
    h.post_approval_response(**K)
    h.on_human_input_resolved(request_id="h1", **H)
    assert [a for a, _ in got] == [True]
    h.on_human_input_resolved(request_id="h2", **H)
    assert [a for a, _ in got] == [True, False]
