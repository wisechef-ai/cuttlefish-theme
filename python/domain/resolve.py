"""CONTRACT §3 — what a reader may show, ``cf2909.resolve/1``. ``now`` and ``pid_alive`` are injected."""

STALE_S = 30
STATES = ("idle", "working", "review", "needs-you", "fault", "unknown")


def resolve(entry, *, now, this_host, pid_alive):
    """Never the last known state: anything doubtful is ``unknown``."""
    if not isinstance(entry, dict):
        return "unknown"
    state = entry.get("state")
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
    return state
