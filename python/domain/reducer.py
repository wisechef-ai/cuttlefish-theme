"""CONTRACT (packages/core/CONTRACT.md) §2 — TUI hook-vocabulary state reducer.

Pure: ``reduce(model, event) -> model``. One model per LINEAGE ROOT (callers pass the root). Events are
``{"t": float, "kind": str, "payload": dict}``; ``kind`` is a hook name or heartbeat | pid_dead | binding.
Mirrors packages/core/domain/state-hook.ts. ``resolve.resolve`` turns a model into a state."""

REVIEW_DWELL_S = 0.6   # pre_verify holds `review` at least this long

_PAYLOAD_KEYS = ("tool_name", "tool_call_id", "session_key", "pattern_key")


def initial():
    return {"in_turn": False, "tools": [], "pending": [], "fault": False, "review_until": None, "finalized": False,
            "last_seen": None, "bound": True, "pid_alive": None}


def _s(v):
    return "" if v is None else str(v)


def _tool_key(p):
    return "tool:" + _s(p.get("tool_call_id"))


def _clarify_key(p):
    return "clarify:" + _s(p.get("tool_call_id"))


def _approval_key(p):
    tcid = p.get("tool_call_id")
    return "approval:" + (_s(tcid) if tcid else _s(p.get("session_key")) + "/" + _s(p.get("pattern_key")))


def _add(xs, k):
    return xs if k in xs else sorted([*xs, k])


def _drop(xs, k):
    return [x for x in xs if x != k]


def reduce(model, ev):
    p = ev.get("payload") or {}
    kind = ev.get("kind")
    m = dict(model, last_seen=ev["t"])           # every event from the session is proof of life
    if kind == "on_session_reset":
        m.update(in_turn=False, tools=[], pending=[], fault=False, review_until=None, finalized=False, pid_alive=None)
    elif kind == "pre_llm_call":
        m.update(in_turn=True, tools=[], fault=False, finalized=False)
    elif kind == "post_llm_call":
        m.update(tools=[], fault=False)
    elif kind == "on_session_end":
        m.update(in_turn=False, tools=[], pending=[], fault=False if p.get("completed") is True else m["fault"])
    elif kind == "on_session_finalize":
        m.update(finalized=True, in_turn=False, tools=[], pending=[])
    elif kind == "pre_tool_call":
        if p.get("tool_name") == "clarify":
            m["pending"] = _add(m["pending"], _clarify_key(p))
        else:
            m["tools"] = _add(m["tools"], _tool_key(p))
    elif kind == "post_tool_call":
        if p.get("tool_name") == "clarify":
            m["pending"] = _drop(m["pending"], _clarify_key(p))
        else:
            m["tools"] = _drop(m["tools"], _tool_key(p))
    elif kind == "pre_approval_request":
        m["pending"] = _add(m["pending"], _approval_key(p))
    elif kind == "post_approval_response":
        m["pending"] = _drop(m["pending"], _approval_key(p))
    elif kind == "api_request_error":
        m["fault"] = True
    elif kind == "pre_verify":
        m["review_until"] = ev["t"] + REVIEW_DWELL_S
    elif kind == "heartbeat":
        m["pid_alive"] = True
    elif kind == "pid_dead":
        m["pid_alive"] = False
    elif kind == "binding":
        m["bound"] = p.get("bound") is True
    return m                                      # on_session_start and anything unrecognised: proof of life only


def normalise(hook, kwargs, ts):
    """Hook kwargs -> the event dict. Only ids and flags survive (no args, no text)."""
    kw = kwargs if isinstance(kwargs, dict) else {}

    def s(name):
        v = kw.get(name)
        return v if isinstance(v, str) else None

    payload = {k: s(k) for k in _PAYLOAD_KEYS if s(k) is not None}
    if isinstance(kw.get("completed"), bool):
        payload["completed"] = kw["completed"]
    return {"t": ts, "kind": hook, "session_id": s("session_id") or s("session_key") or "", "payload": payload}
