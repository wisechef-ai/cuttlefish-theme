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
class _Member:
    """One open request on one side (an approval-hook open or a human input)."""

    rid: str
    session_id: str
    kind: str
    pair: "_Pair | None" = None
    t: float = field(default_factory=lambda: _clock())


@dataclass(eq=False)
class _Pair:
    """A human input and an approval hook counting as ONE question.

    ``rid``/``session_id``/``kind`` are the FIRST-opened member's: it already
    emitted the pair's ``active:true``, so the ``active:false`` must match it.
    """

    rid: str
    session_id: str
    kind: str
    hook_closed: bool = False
    human_closed: bool = False


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


def _emit(active: bool, member: _Member | _Pair, session_key: str) -> None:
    events.emit("needs_you", {
        "session_id": member.session_id,
        "session_key": session_key,
        "request_id": member.rid,
        "kind": member.kind,
        "active": active,
    })


def _close_counted(registry: dict, waiting: dict, session_key: str, rid: str, hook_side: bool) -> None:
    """One counted close: consume the oldest open member behind the key.

    Unpaired: the desktop's ``active:false`` comes when the LAST open request
    with this key closes (the multiset). Paired: only when both halves of the
    pair have closed — and then with the pair's (first-opened) identity.
    """
    member = _pop_oldest(registry, (session_key, rid))
    if member is None:
        return  # a close with nothing open: emit nothing, never go negative
    _discard(waiting, session_key, member)
    pair = member.pair
    if pair is None:
        if (session_key, rid) not in registry:
            _emit(False, member, session_key)
        return
    if hook_side:
        pair.hook_closed = True
    else:
        pair.human_closed = True
    if pair.hook_closed and pair.human_closed:
        _emit(False, pair, session_key)


def _pair_up(member: _Member, partner: _Member) -> None:
    """Join two open requests into one counted question (both stay closable)."""
    pair = _Pair(rid=partner.rid, session_id=partner.session_id, kind=partner.kind)
    partner.pair = pair
    member.pair = pair


def _open_counted(registry: dict, waiting: dict, other_waiting: dict, session_key: str, rid: str,
                  session_id: str, kind: str, pairable: bool) -> None:
    """One counted open, on either side. Both sides open the same way: append a
    member to the key's multiset, pair with the oldest unpaired partner from the
    OTHER side when one waits (the pair's ``active:true`` was the partner's, so
    nothing is emitted), else wait yourself; only the first member with this key
    is a NEW question (0→1)."""
    _prune(_clock())
    member = _Member(rid=rid, session_id=session_id, kind=kind)
    queue = registry.setdefault((session_key, rid), deque())
    first = not queue
    queue.append(member)
    partner = _pop_oldest(other_waiting, session_key) if pairable else None
    if partner is not None:
        _pair_up(member, partner)
        return
    if pairable:
        waiting.setdefault(session_key, deque()).append(member)
    if first:
        _emit(True, member, session_key)


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
    a human input (``request``/``resolved``). One shared shape — the only
    differences are which registry holds the member and which half of a pair
    it closes.
    """
    _prune(_clock())
    registry = _hooks if hook_side else _humans
    waiting = _waiting_hooks if hook_side else _waiting_humans
    _close_counted(registry, waiting, session_key, rid, hook_side)


_reset()
events.on_broadcaster_change(_reset)  # a re-attached observer starts a fresh slate
