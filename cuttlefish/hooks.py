"""Observer hooks: approval / human-input / api-error → desktop events.

Every function here is registered by ``register.py`` and is an OBSERVER: it must
never raise, never block, and never broadcast prompt, command or error TEXT
(secrets live there). The kwargs are the producers' own at v0.22.7 —
``tools/human_input_hooks.py`` (human input, uuid request id),
``tools/approval_context.py`` + ``approval_gateway_wait.py`` + ``approval_prompt.py``
(approval pre/post), ``agent/api_request_hooks.py`` (api errors) — so we copy
named fields out and never echo kwargs back.

Request identity: the desktop keys open requests by ``(session, request id)``.
The transport path supplies its own ``request_id``; the gateway and MCP
elicitation paths carry none, so one is derived — deterministically, across
processes — over exactly ``(session_key, turn_id, tool_call_id, pattern_key,
surface)``, blind to the command text. A coalesced follower (``coalesced=True``)
sits behind its leader and emits nothing: not a second request, and never a
close of what the leader still holds. Whether an open/close is EMITTED is
``pairing``'s ruling (part 2): a multiset per request key, and one human
question counting once however the producers interleave.
"""

from __future__ import annotations

import functools
import hashlib
from typing import Any, Callable

from . import events, pairing

#: The five kwargs the derived approval key is computed over (nothing else).
KEY_FIELDS = ("session_key", "turn_id", "tool_call_id", "pattern_key", "surface")
#: The only ``kind`` values that ride the wire (the producers' own literals);
#: anything else is producer text we must not echo, so it travels as "other".
KINDS = ("approval", "clarify", "sudo")


def _observer(fn: Callable[..., None]) -> Callable[..., None]:
    """Wrap a hook so it can NEVER raise: an observer must not break its host."""
    @functools.wraps(fn)
    def wrapper(**kwargs: Any) -> None:
        try:
            fn(**kwargs)
        except Exception:
            pass
    return wrapper


def _session_id(kwargs: dict[str, Any]) -> str | None:
    """The session a desktop row can attribute the event to, or None.

    Only the producer's own ``session_id`` counts — never one guessed out of
    ``session_key``: an event the desktop cannot place is not sent (O3.8)."""
    sid = kwargs.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def _text(kwargs: dict[str, Any], key: str) -> str:
    value = kwargs.get(key)
    return value if isinstance(value, str) else ""


def _kind(kwargs: dict[str, Any]) -> str:
    """The wire ``kind``: a known producer literal, "approval" when absent, else "other"."""
    kind = _text(kwargs, "kind")
    if not kind:
        return "approval"
    return kind if kind in KINDS else "other"


def _request_key(kwargs: dict[str, Any]) -> str:
    """The request id the desktop sees for an approval hook call.

    The producer's ``request_id`` when the call carries a non-empty one (the
    plugin-transport path), else a stable digest over :data:`KEY_FIELDS` —
    identical for a request's pre and post, deterministic across processes
    (``hashlib``, never the salted builtin ``hash()``), and independent of the
    command text, description, choice or any other kwarg."""
    rid = kwargs.get("request_id")
    if isinstance(rid, str) and rid:
        return rid
    joined = "\x1f".join(_text(kwargs, field) for field in KEY_FIELDS)
    return "cf-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _fire_approval(kwargs: dict[str, Any], active: bool) -> None:
    """pre/post of an approval request → needs_you on/off (counted, paired)."""
    session_id = _session_id(kwargs)
    if session_id is None or kwargs.get("coalesced"):
        return  # unattributable, or a follower behind its leader: an alias, never a second count
    key = (_text(kwargs, "session_key"), _request_key(kwargs))
    if active:
        pairing.approval_open(*key, session_id, _kind(kwargs))
    else:
        pairing.close(*key, hook_side=True)


def _fire_human_input(kwargs: dict[str, Any], active: bool) -> None:
    """request/resolved of the human-input wrapper → needs_you on/off (counted, paired)."""
    session_id = _session_id(kwargs)
    if session_id is None:
        return
    key = (_text(kwargs, "session_key"), _request_key(kwargs))
    if active:
        pairing.human_open(*key, session_id, _kind(kwargs))
    else:
        pairing.close(*key, hook_side=False)


@_observer
def pre_approval_request(**kwargs: Any) -> None:
    """An approval is about to be asked (gateway, transport or MCP elicitation)."""
    _fire_approval(kwargs, True)


@_observer
def post_approval_response(**kwargs: Any) -> None:
    """An approval was answered, timed out or withdrawn."""
    _fire_approval(kwargs, False)


@_observer
def on_human_input_request(**kwargs: Any) -> None:
    """The user is being asked something (approval wrapper, clarify, ...)."""
    _fire_human_input(kwargs, True)


@_observer
def on_human_input_resolved(**kwargs: Any) -> None:
    """The ask from :func:`on_human_input_request` settled."""
    _fire_human_input(kwargs, False)


@_observer
def api_request_error(**kwargs: Any) -> None:
    """A model call failed. Only a KNOWN-final failure (``retryable`` False) is
    news: a retryable or unknown error may still see the turn succeed."""
    session_id = _session_id(kwargs)
    if kwargs.get("retryable") is not False or session_id is None:
        return
    events.emit("error", {
        "session_id": session_id,
        "session_key": _text(kwargs, "session_key"),
        "retryable": False,  # never the error text: secrets
    })
