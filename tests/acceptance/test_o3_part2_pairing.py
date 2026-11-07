"""ACCEPTANCE CONTRACT PART 2 — O3 collisions and ONE-human-ONE-count pairing (closes luna-parts L1, L2) (locked with the parts).

Part 1 pinned a derived request key. Two holes remained: (L1) two live requests can derive the SAME key (empty
     turn_id/tool_call_id, concurrent
identical approvals), so one post could close both; (L2) a gateway approval fires BOTH an on_human_input_request wrapper and a
pre_approval_request, and part 1 only proved the pair "eventually closes", not that one human question counts once.

RULES (binding), observed on the desktop as the stream of needs_you events keyed by (session_id, request_id):
 L1  The Python half keeps a MULTISET per derived key: a request open increments, a close decrements; `active:true` is
      emitted on 0→1 and
     `active:false` on 1→0. Empty / None key fields hash as "" (stable); a close with nothing open emits nothing (never negative).
 L2  Per session_key, a human_input(kind=approval) request and a NON-coalesced approval-hook request opened while the
      other is open and UNPAIRED
     (oldest first) form ONE pair: the first-opened member emits active:true (with ITS request id); the pair emits
          active:false only when BOTH
     members have closed (with that same id). A coalesced follower (coalesced=True) is an alias of its leader and emits
          nothing, and is never
     a pairing partner. Two human_input requests are never paired with each other (two concurrent approvals in one session count 2).
The kwargs are those of part 1 (copied from the v0.22.7 producers). Every step asserts the events it emitted AND the
     open count after it.
"""
from __future__ import annotations

import importlib

import pytest

from .helpers import plugin_package
from .test_o3_part1_approval_keys import ELICIT, GATEWAY, HUMAN, SID, TRANSPORT

HUMAN2 = {**HUMAN, "request_id": "2b77aa01"}
GATEWAY2 = {**GATEWAY, "tool_call_id": "c2"}
H1, H2, R = HUMAN["request_id"], HUMAN2["request_id"], TRANSPORT["request_id"]


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


def h_open(**kw):
    hooks().on_human_input_request(**kw)


def h_close(**kw):
    hooks().on_human_input_resolved(**kw, outcome="once")


def pre(**kw):
    hooks().pre_approval_request(**kw)


def post(**kw):
    hooks().post_approval_response(**kw, choice="once")


def open_count(sent) -> int:
    live: set[tuple[str, str]] = set()
    for _, e, p in sent:
        if e == "needs_you":
            (live.add if p["active"] else live.discard)((p["session_id"], p["request_id"]))
    return len(live)


def run(sent, steps):
    """steps: (label, callable, [(active, who)…] emitted by THIS step, open count after). who: H1 H2 R or D (the derived
    key, any stable id)."""
    derived: list[str] = []
    for label, fn, want, open_after in steps:
        n = len(sent)
        fn()
        got = [(p["active"], p["request_id"]) for _, e, p in sent[n:] if e == "needs_you"]
        assert len(got) == len(want), f"{label}: emitted {got}, expected {want}"
        for (active, rid), (w_active, who) in zip(got, want, strict=True):
            assert active is w_active, f"{label}: active={active}, expected {w_active}"
            if who == "D":
                assert rid and rid not in (H1, H2, R), f"{label}: a derived key was expected, got {rid}"
                derived.append(rid)
                assert rid == derived[0], f"{label}: the derived key changed ({rid} vs {derived[0]})"
            else:
                assert rid == {"H1": H1, "H2": H2, "R": R}[who], f"{label}: request id {rid} is not {who}"
        assert open_count(sent) == open_after, f"{label}: {open_count(sent)} open after the step, expected {open_after}"


# ---- L1 collisions ------------------------------------------------------------------------------------------------------

def test_P2_1_two_colliding_pre_and_one_post_leave_it_open_until_the_second_post(sent):
    run(sent, [("pre#1", lambda: pre(**GATEWAY), [(True, "D")], 1),
               ("pre#2 (same derived key)", lambda: pre(**GATEWAY), [], 1),
               ("post#1", lambda: post(**GATEWAY), [], 1),
               ("post#2", lambda: post(**GATEWAY), [(False, "D")], 0)])


def test_P2_2_empty_or_missing_key_fields_hash_the_same_and_pair_up(sent):
    empty = {**GATEWAY, "turn_id": "", "tool_call_id": ""}
    none = {**GATEWAY, "turn_id": None, "tool_call_id": None}
    run(sent, [("pre (empty fields)", lambda: pre(**empty), [(True, "D")], 1),
               ("post (None fields: same key)", lambda: post(**none), [(False, "D")], 0)])


def test_P2_3_a_close_with_nothing_open_emits_nothing_and_never_goes_negative(sent):
    run(sent, [("stray post", lambda: post(**GATEWAY), [], 0),
               ("pre afterwards", lambda: pre(**GATEWAY), [(True, "D")], 1),
               ("post", lambda: post(**GATEWAY), [(False, "D")], 0),
               ("second stray post", lambda: post(**GATEWAY), [], 0)])


def test_P2_4_different_keys_do_not_interfere_while_a_collision_is_open(sent):
    pre(**GATEWAY)
    pre(**GATEWAY2)
    assert open_count(sent) == 2
    post(**GATEWAY)
    assert open_count(sent) == 1
    post(**GATEWAY2)
    assert open_count(sent) == 0


# ---- L2 pairing: the three real producer orders ---------------------------------------------------------------------------

def test_P2_5_gateway_order_H_open_pre_post_H_resolved_counts_once(sent):
    run(sent, [("H open", lambda: h_open(**HUMAN), [(True, "H1")], 1),
               ("pre (pairs with H)", lambda: pre(**GATEWAY), [], 1),
               ("post (H still open)", lambda: post(**GATEWAY), [], 1),
               ("H resolved (both closed)", lambda: h_close(**HUMAN), [(False, "H1")], 0)])


def test_P2_6_transport_order_pre_R_H_open_H_resolved_post_R_counts_once(sent):
    run(sent, [("pre(R)", lambda: pre(**TRANSPORT), [(True, "R")], 1),
               ("H open (pairs with pre)", lambda: h_open(**HUMAN), [], 1),
               ("H resolved (pre still open)", lambda: h_close(**HUMAN), [], 1),
               ("post(R) (both closed)", lambda: post(**TRANSPORT), [(False, "R")], 0)])


def test_P2_7_elicitation_pre_post_without_a_wrapper(sent):
    run(sent, [("pre", lambda: pre(**ELICIT), [(True, "D")], 1), ("post", lambda: post(**ELICIT), [(False, "D")], 0)])


def test_P2_8_two_concurrent_gateway_approvals_in_one_session_count_two(sent):
    run(sent, [("H1 open", lambda: h_open(**HUMAN), [(True, "H1")], 1),
               ("pre1 pairs with H1", lambda: pre(**GATEWAY), [], 1),
               ("H2 open (humans never pair)", lambda: h_open(**HUMAN2), [(True, "H2")], 2),
               ("pre2 pairs with H2", lambda: pre(**GATEWAY2), [], 2),
               ("post1", lambda: post(**GATEWAY), [], 2),
               ("H1 resolved", lambda: h_close(**HUMAN), [(False, "H1")], 1),
               ("post2", lambda: post(**GATEWAY2), [], 1),
               ("H2 resolved", lambda: h_close(**HUMAN2), [(False, "H2")], 0)])


def test_P2_9_interleaved_opens_pair_oldest_first(sent):
    run(sent, [("H1 open", lambda: h_open(**HUMAN), [(True, "H1")], 1),
               ("H2 open", lambda: h_open(**HUMAN2), [(True, "H2")], 2),
               ("pre1 pairs with the OLDEST unpaired (H1)", lambda: pre(**GATEWAY), [], 2),
               ("pre2 pairs with H2", lambda: pre(**GATEWAY2), [], 2),
               ("H2 resolved, post2 outstanding", lambda: h_close(**HUMAN2), [], 2),
               ("post2", lambda: post(**GATEWAY2), [(False, "H2")], 1),
               ("post1", lambda: post(**GATEWAY), [], 1),
               ("H1 resolved", lambda: h_close(**HUMAN), [(False, "H1")], 0)])


def test_P2_10_a_coalesced_follower_is_an_alias_emits_nothing_and_is_never_a_partner(sent):
    follower = {**GATEWAY, "tool_call_id": "c3"}
    run(sent, [("H1 open", lambda: h_open(**HUMAN), [(True, "H1")], 1),
               ("leader pre pairs", lambda: pre(**GATEWAY), [], 1),
               ("follower pre (coalesced)", lambda: pre(**follower, coalesced=True), [], 1),
               ("H2 open: the follower is NOT its partner", lambda: h_open(**HUMAN2), [(True, "H2")], 2),
               ("follower post (coalesced)", lambda: post(**follower, coalesced=True), [], 2),
               ("leader post", lambda: post(**GATEWAY), [], 2),
               ("H1 resolved", lambda: h_close(**HUMAN), [(False, "H1")], 1),
               ("H2 resolved", lambda: h_close(**HUMAN2), [(False, "H2")], 0)])


def test_P2_11_pairing_is_per_session_key(sent):
    other = {**GATEWAY, "session_key": GATEWAY["session_key"] + "-b", "session_id": SID + "b"}
    run(sent, [("H open in session A", lambda: h_open(**HUMAN), [(True, "H1")], 1),
               ("pre in session B does not pair", lambda: pre(**other), [(True, "D")], 2)])


def test_P2_12_a_human_request_that_is_not_an_approval_never_pairs(sent):
    clarify = {**HUMAN, "kind": "clarify", "request_id": "c7"}
    h_open(**clarify)
    pre(**GATEWAY)
    assert open_count(sent) == 2, "a clarify question and an approval are two things the user must answer"
