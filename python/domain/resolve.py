"""CONTRACT (packages/core/CONTRACT.md) §2 resolve — what a reader may show. ``now`` is injected.

``resolve(model, now)`` is the contract function. ``resolve_entry`` applies the same rules to a bus file
(§5 entry), where the owner pid is probed instead of replaying liveness events."""

STALE_S = 20.0   # the bus heartbeats every 5 s while the owner lives
STATES = ("idle", "thinking", "tool", "review", "needs-you", "fault", "unknown")
# Does the host's event stream tell a tool from the model thinking? (CONTRACT §2/§3.) A surface without the
# signal maps busy -> thinking; `hermes cuttlefish doctor` prints this table.
TOOL_SIGNAL = {"tui": True, "desktop": True}


def resolve(model, now):
    """First match wins. "Turn ended" is never needs-you; stale is never the last known state."""
    if (model["last_seen"] is None or model["finalized"] or model["pid_alive"] is False
            or model["bound"] is False or now - model["last_seen"] > STALE_S):
        return "unknown"
    if model["pending"]:
        return "needs-you"
    if model["fault"]:
        return "fault"
    if model["in_turn"]:
        return "tool" if model.get("tools") else "thinking"
    if model["review_until"] is not None and now < model["review_until"]:
        return "review"
    return "idle"


def resolve_entry(entry, *, now, this_host, pid_alive):
    """Never the last known state: anything doubtful is ``unknown``."""
    if not isinstance(entry, dict):
        return "unknown"
    state = entry.get("state")
    if state == "working":                   # a cf2909.bus/1 entry: busy, no tool signal -> thinking
        state = "thinking"
    if state not in STATES or state == "unknown":  # finalized entries carry state unknown
        return "unknown"
    hb = entry.get("heartbeat")
    if isinstance(hb, bool) or not isinstance(hb, (int, float)):
        return "unknown"
    if now - hb > STALE_S:
        return "unknown"
    if entry.get("owner_host") == this_host:
        pid = entry.get("owner_pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or not pid_alive(pid):
            return "unknown"
    if state == "review":                    # the pulse ends with no event: the entry carries its deadline
        until = entry.get("review_until")
        if isinstance(until, (int, float)) and not isinstance(until, bool) and now >= until:
            return "idle"
    return state
