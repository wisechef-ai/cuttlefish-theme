"""Counted requests: a multiset per request key, and ONE human question = ONE count.

Contract part 2 (ruling R-P2), on top of part 1's derived request keys:

L1 — collisions: a MULTISET per derived key. An open increments, a close
decrements; ``active:true`` is emitted on 0→1 and ``active:false`` on 1→0, so
two colliding requests stay open until BOTH closed and one post can never
close both. A close with nothing open emits nothing — the count never goes
negative. Empty and ``None`` key fields hash as ``""`` (hooks' ``_text``),
which is what makes the empty-field and None-field calls the SAME key.

L2 — pairing: per ``session_key``, a ``human_input(kind=approval)`` request
and a NON-coalesced approval-hook request opened while the other is open and
UNPAIRED form ONE pair (oldest first). The first-opened member emitted the
pair's ``active:true`` with ITS request id; the pair emits ``active:false``
(that same id) only when BOTH members have closed — one human question counts
once however the producers fire around it. A coalesced follower never reaches
this module (hooks drop it: an alias of its leader). Two human inputs never
pair with each other, and a human input that is not an approval (a clarify)
never pairs: both are plain counted requests.

The state is per process, in memory, and bounded: every record carries its
open time and anything older than :data:`TTL_S` (24 h) is dropped, so a crash
mid-approval cannot leak memory forever. Pruning never emits. Re-attaching an
observer (``events.set_broadcaster``) starts a fresh slate — the seam tests
isolate on; production attaches once and never again.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from . import events

#: A request nobody closes for a day is a crashed process's leftovers.
TTL_S = 24 * 60 * 60
#: Injectable so the TTL bound is testable without waiting.
_clock: Callable[[], float] = time.time


@dataclass(eq=False)
class _Slot:
    """One question as the desktop sees it: the identity its ``active:true`` was
    emitted under and how many open requests still share it. ``active:false``
    goes out (under that same identity) only when ``open`` returns to 0."""

    rid: str
    session_id: str
    kind: str
    open: int = 0


@dataclass(eq=False)
class _Member:
    """One open request on one side (an approval-hook open or a human input)."""

    slot: _Slot
    t: float = field(default_factory=lambda: _clock())


_hooks: dict[tuple[str, str], deque[_Member]] = {}    # approval side, per (session_key, rid)
_humans: dict[tuple[str, str], deque[_Member]] = {}   # human side, per (session_key, rid)
_waiting_humans: dict[str, deque[_Member]] = {}       # per session_key: open, unpaired, approval
_waiting_hooks: dict[str, deque[_Member]] = {}        # per session_key: open, unpaired, non-coalesced


def _reset() -> None:
    """Empty every registry (a new observer starts from a clean slate)."""
    for registry in (_hooks, _humans, _waiting_humans, _waiting_hooks):
        registry.clear()


def _prune(now: float) -> None:
    """Drop every record open for longer than :data:`TTL_S`, emitting nothing."""

    def fresh(member: _Member) -> bool:
        return now - member.t <= TTL_S

    for registry in (_hooks, _humans, _waiting_humans, _waiting_hooks):
        for key in list(registry):
            registry[key] = deque(m for m in registry[key] if fresh(m))
            if not registry[key]:
                del registry[key]


def _pop_oldest(mapping: dict[Any, deque[_Member]], key: Any) -> _Member | None:
    """The oldest open member behind *key* (a counted close consumes one), if any."""
    queue = mapping.get(key)
    if not queue:
        return None
    member = queue.popleft()
    if not queue:
        del mapping[key]
    return member


def _discard(mapping: dict[Any, deque[_Member]], key: Any, member: _Member) -> None:
    """Take *member* out of a waiting queue it no longer belongs in (identity)."""
    queue = mapping.get(key)
    if queue is not None and member in queue:
        queue.remove(member)
        if not queue:
            del mapping[key]


def _emit(active: bool, slot: _Slot, session_key: str) -> None:
    events.emit("needs_you", {
        "session_id": slot.session_id,
        "session_key": session_key,
        "request_id": slot.rid,
        "kind": slot.kind,
        "active": active,
    })


def _close_counted(registry: dict, waiting: dict, session_key: str, rid: str) -> None:
    """One counted close: consume the oldest open member behind the key and
    release its slot; the slot's ``active:false`` comes when the LAST request
    sharing it (a colliding key, a paired partner) has closed."""
    member = _pop_oldest(registry, (session_key, rid))
    if member is None:
        return  # a close with nothing open: emit nothing, never go negative
    _discard(waiting, session_key, member)
    member.slot.open -= 1
    if member.slot.open == 0:
        _emit(False, member.slot, session_key)


def _slot_for(registry: dict, other_waiting: dict, session_key: str, rid: str,
              session_id: str, kind: str, pairable: bool) -> tuple[_Slot, bool, bool]:
    """The slot a new open joins, whether it is a NEW question (0→1), whether it paired.

    The oldest unpaired partner from the OTHER side wins (a pair is one
    question, its ``active:true`` was the partner's); else a colliding open of
    the same key shares that open's slot; else a fresh slot."""
    partner = _pop_oldest(other_waiting, session_key) if pairable else None
    if partner is not None:
        return partner.slot, False, True
    colliding = registry.get((session_key, rid))
    if colliding:
        return colliding[0].slot, False, False
    return _Slot(rid=rid, session_id=session_id, kind=kind), True, False


def _open_counted(registry: dict, waiting: dict, other_waiting: dict, session_key: str, rid: str,
                  session_id: str, kind: str, pairable: bool) -> None:
    """One counted open, on either side: join (or start) a slot, wait for a
    partner when pairable, and emit ``active:true`` only for a new question."""
    _prune(_clock())
    slot, new, paired = _slot_for(registry, other_waiting, session_key, rid, session_id, kind, pairable)
    slot.open += 1
    member = _Member(slot=slot)
    registry.setdefault((session_key, rid), deque()).append(member)
    if pairable and not paired:
        waiting.setdefault(session_key, deque()).append(member)
    if new:
        _emit(True, slot, session_key)


def approval_open(session_key: str, rid: str, session_id: str, kind: str) -> None:
    """An approval-hook request opened (non-coalesced, attributable)."""
    _open_counted(_hooks, _waiting_hooks, _waiting_humans, session_key, rid, session_id, kind, pairable=True)


def human_open(session_key: str, rid: str, session_id: str, kind: str) -> None:
    """A human-input request opened (``kind=approval`` pairs; a clarify never does)."""
    _open_counted(_humans, _waiting_humans, _waiting_hooks, session_key, rid, session_id, kind,
                  pairable=kind == "approval")


def close(session_key: str, rid: str, hook_side: bool) -> None:
    """A counted close on one side of the wire.

    ``hook_side=True``: an approval-hook request (``pre``/``post``); ``False``:
    a human input (``request``/``resolved``): which registry holds the member.
    """
    _prune(_clock())
    registry = _hooks if hook_side else _humans
    waiting = _waiting_hooks if hook_side else _waiting_humans
    _close_counted(registry, waiting, session_key, rid)


_reset()
events.on_broadcaster_change(_reset)  # a re-attached observer starts a fresh slate
