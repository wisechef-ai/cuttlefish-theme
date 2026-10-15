"""CONTRACT §2 — state reducer, ``cf2909.state/1``. Pure: events in, states out."""

EVENT_KEYS = ("hook", "ts", "session_id", "tool_name", "tool_call_id", "turn_id", "completed")


def normalise(hook, kwargs, ts):
    """Hook kwargs -> the normalised event dict. Only ids and flags survive (no args, no text)."""
    kw = kwargs if isinstance(kwargs, dict) else {}

    def s(name):
        v = kw.get(name)
        return v if isinstance(v, str) else None

    sid = s("session_id") or s("session_key") or ""
    completed = kw.get("completed")
    return {"hook": hook, "ts": ts, "session_id": sid, "tool_name": s("tool_name"),
            "tool_call_id": s("tool_call_id"), "turn_id": s("turn_id"),
            "completed": completed if isinstance(completed, bool) else None}


def initial():
    return {"base": "idle", "pending": [], "fault": False, "finalized": False}


def output(st):
    if st["finalized"]:
        return "unknown"
    if st["pending"]:
        return "needs-you"
    if st["fault"]:
        return "fault"
    return st["base"]


def _approval_key(ev):
    return "approval:" + (ev.get("tool_call_id") or ev.get("turn_id") or "")


def step(st, ev):
    """Return the next reducer state (the input is not mutated)."""
    st = {"base": st["base"], "pending": list(st["pending"]), "fault": st["fault"], "finalized": st["finalized"]}
    hook = ev.get("hook")
    if hook == "on_session_reset":
        return initial()
    if hook == "on_session_start":
        st["finalized"] = False
    elif hook == "pre_llm_call":
        st.update(base="working", pending=[], fault=False, finalized=False)
    elif hook == "pre_verify":
        if st["base"] == "working":
            st["base"] = "review"
    elif hook == "post_llm_call":
        st["fault"] = False
        if st["base"] == "review":
            st["base"] = "working"
    elif hook == "on_session_end":
        st["base"], st["pending"] = "idle", []
        if ev.get("completed") is True:
            st["fault"] = False
    elif hook == "pre_tool_call" and ev.get("tool_name") == "clarify":
        key = "clarify:" + (ev.get("tool_call_id") or "")
        if key not in st["pending"]:
            st["pending"].append(key)
    elif hook == "post_tool_call" and ev.get("tool_name") == "clarify":
        key = "clarify:" + (ev.get("tool_call_id") or "")
        st["pending"] = [k for k in st["pending"] if k != key]
    elif hook == "pre_approval_request":
        key = _approval_key(ev)
        if key not in st["pending"]:
            st["pending"].append(key)
    elif hook == "post_approval_response":
        key = _approval_key(ev)
        st["pending"] = [k for k in st["pending"] if k != key]
    elif hook == "api_request_error":
        st["fault"] = True
    elif hook == "on_session_finalize":
        st["finalized"] = True
    return st


def fold(events, st=None, since=None):
    """Run events through the reducer. Returns ([{"state","since"}...], final reducer state).

    ``since`` is the ts of the event that last CHANGED the output state."""
    st = st if st is not None else initial()
    prev = output(st)
    out = []
    for ev in events:
        st = step(st, ev)
        cur = output(st)
        if cur != prev or since is None:
            since = ev.get("ts")
        prev = cur
        out.append({"state": cur, "since": since})
    return out, st
