"""Unit: cuttlefish.pairing — the count, the pair, and the 24 h bound.

The locked part-2 file pins the producer-faithful interleavings; these pin the
edges it leaves open: the TTL bound (a crashed process cannot leak memory
forever, and pruning itself never emits) and the state-isolation seam (each
observer starts from zero).
"""

from __future__ import annotations

import pytest
from cuttlefish_theme.cuttlefish import events, pairing

SK = "agent:main:desktop:dm:20261105"
SID = "20261105"


@pytest.fixture
def sent():
    got: list[tuple[str, dict]] = []
    events.set_broadcaster(lambda _pid, event, payload=None: got.append((event, dict(payload or {}))))
    yield got
    events.set_broadcaster(None)


def actives(sent):
    return [(e, p["active"], p["request_id"]) for e, p in sent if e == "needs_you"]


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock: advance(offset) moves time forward by offset seconds."""
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(pairing, "_clock", lambda: state["now"])

    def advance(offset: float) -> float:
        state["now"] += offset
        return state["now"]

    return advance


def test_a_fresh_record_still_pairs_just_before_the_ttl(sent, clock):
    pairing.human_open(SK, "h1", SID, "approval")
    assert actives(sent) == [("needs_you", True, "h1")]
    clock(pairing.TTL_S - 1)  # alive for 24 h minus a second: still pairable
    pairing.approval_open(SK, "r1", SID, "approval")
    assert actives(sent) == [("needs_you", True, "h1")], "it paired instead of opening a second question"


def test_a_record_exactly_at_the_ttl_is_still_fresh(sent, clock):
    pairing.human_open(SK, "h1", SID, "approval")
    clock(pairing.TTL_S)  # exactly 24 h old: stale is strictly OLDER than the TTL
    pairing.approval_open(SK, "r1", SID, "approval")
    assert actives(sent) == [("needs_you", True, "h1")], "at exactly the TTL it still pairs"


def test_records_older_than_the_ttl_are_dropped_not_paired(sent, clock):
    pairing.human_open(SK, "h1", SID, "approval")
    clock(pairing.TTL_S + 1)  # a day and a second: a crashed process's leftover
    pairing.approval_open(SK, "r1", SID, "approval")
    assert actives(sent) == [("needs_you", True, "h1"), ("needs_you", True, "r1")], \
        "the stale human is gone: the approval opens a fresh question instead of pairing"
    pairing.close(SK, "h1", hook_side=False)  # its close, a day late, finds nothing: no false for a dropped record
    pairing.close(SK, "r1", hook_side=True)
    assert actives(sent) == [("needs_you", True, "h1"), ("needs_you", True, "r1"), ("needs_you", False, "r1")]
    for registry in (pairing._hooks, pairing._humans, pairing._waiting_humans, pairing._waiting_hooks):
        assert registry == {}, "state is bounded: emptied queues leave no skeleton entries"


def test_a_closed_request_is_not_a_pairing_partner(sent):
    """A request that opened and closed leaves the waiting queue: the next
    human input is its OWN question, not the ghost's pair."""
    pairing.approval_open(SK, "r1", SID, "approval")
    pairing.close(SK, "r1", hook_side=True)
    pairing.human_open(SK, "h1", SID, "approval")
    assert actives(sent) == [("needs_you", True, "r1"), ("needs_you", False, "r1"), ("needs_you", True, "h1")]


def test_pruning_itself_never_emits(sent, clock):
    pairing.human_open(SK, "h1", SID, "approval")
    pairing.approval_open(SK, "r1", SID, "approval")  # paired (h1 first)
    clock(pairing.TTL_S + 1)
    pairing.close("nowhere", "nobody", hook_side=False)  # any event prunes; this one also emits nothing
    assert actives(sent) == [("needs_you", True, "h1")], "the prune dropped the pair without a word"


def test_a_new_observer_starts_from_a_clean_slate(sent):
    pairing.human_open(SK, "h1", SID, "approval")
    events.set_broadcaster(None)  # re-attach: the seam production never hits
    got: list[tuple[str, dict]] = []
    events.set_broadcaster(lambda _pid, event, payload=None: got.append((event, dict(payload or {}))))
    pairing.approval_open(SK, "r1", SID, "approval")
    assert [(e, p["active"]) for e, p in got if e == "needs_you"] == [("needs_you", True)], \
        "no state from the previous observer: a fresh open is a fresh question"


def flags(sent):
    return [active for _e, active, _rid in actives(sent)]


def test_two_humans_and_a_clarify_never_pair_with_each_other(sent):
    pairing.human_open(SK, "h1", SID, "approval")
    pairing.human_open(SK, "h2", SID, "approval")
    pairing.human_open(SK, "c7", SID, "clarify")
    assert flags(sent) == [True, True, True]
    pairing.approval_open(SK, "r1", SID, "approval")  # pairs with h1 only: one question absorbed
    assert flags(sent) == [True, True, True], "the pair's true was h1's"
    pairing.close(SK, "r1", hook_side=True)
    pairing.close(SK, "h1", hook_side=False)  # both halves of the pair closed → one false
    assert flags(sent) == [True, True, True, False]
