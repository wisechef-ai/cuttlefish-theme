"""Replay a recorded trace (packages/core/CONTRACT.md §4) through the hook reducer.

Mirrors packages/core/app/replay.ts for ``host: tui`` traces: per lineage root, the resolved state at every
event instant and at synthetic ticks every ``step_s``. Pure: all time comes from the trace. Used by the
cross-language parity test and by doctor-style tooling."""
import json
import math

from . import allocator, reducer
from . import resolve as resolver

TAIL_S = resolver.STALE_S + 5
_ANY_SRC = {"heartbeat", "pid_dead", "binding"}


def _non_blank(s):
    return isinstance(s, str) and s.strip() != ""


def _utf16(s):
    return s.encode("utf-16-be", "surrogatepass")


def replay(trace_lines, step_s=1):
    if not (step_s > 0) or not math.isfinite(step_s):
        raise ValueError(f"step_s must be a positive number, got {step_s}")
    objs = [json.loads(l) if isinstance(l, str) else l for l in trace_lines if not (isinstance(l, str) and not l.strip())]
    head = objs[0] if objs else None
    if not head or head.get("src") != "meta" or head.get("kind") != "trace":
        raise ValueError('trace has no header line (src "meta", kind "trace")')
    host = "desktop" if head.get("host") == "desktop" else "tui"
    if host != "tui":
        raise ValueError("only host: tui traces are replayed by the Python half")

    roots, models, trackers, slots_by_profile = {}, {}, {}, {}
    skipped = 0

    def ensure_root(key, profile):
        if key in roots:
            return
        peers = slots_by_profile.setdefault(profile, [])
        a = allocator.allocate(key, peers)
        peers.append(a.slot)
        roots[key] = {"profile": profile, "identity": {"slot": a.slot, "hue_deg": a.hue_deg, "crowded": a.crowded},
                      "samples": []}
        trackers[key] = {"state": None, "since": 0}

    lines = []
    for i, o in enumerate(objs[1:]):
        if not o or o.get("src") == "meta":
            continue
        t = o.get("t")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            raise ValueError(f'trace line {i + 2} has no finite "t"')
        lines.append((t, i, {"t": t, "src": str(o.get("src") or ""), "kind": str(o.get("kind") or ""),
                             "profile": o["profile"] if _non_blank(o.get("profile")) else "default",
                             "session": o.get("session"), "lineage_root": o.get("lineage_root"),
                             "payload": o.get("payload") or {}}))
    lines.sort(key=lambda x: (x[0], x[1]))

    def apply(l):
        nonlocal skipped
        relevant = l["src"] == "hook" or (l["kind"] in _ANY_SRC and not l["src"].startswith("desktop."))
        if not relevant:
            return []
        key = l["lineage_root"] if _non_blank(l["lineage_root"]) else (l["session"] if _non_blank(l["session"]) else None)
        if key is None:
            skipped += 1
            return []
        ensure_root(key, l["profile"])
        models[key] = reducer.reduce(models.get(key) or reducer.initial(),
                                     {"t": l["t"], "kind": l["kind"], "payload": l["payload"]})
        return [key]

    def sample(key, t, on):
        state = resolver.resolve(models[key], t)
        tr = trackers[key]
        if tr["state"] != state:
            tr = trackers[key] = {"state": state, "since": t}
        roots[key]["samples"].append({"t": t, "on": on, "state": state, "since": tr["since"]})

    k = math.ceil(lines[0][0] / step_s) if lines else 0

    def tick_to(t):
        nonlocal k
        while k * step_s <= t:
            for key in list(roots):
                sample(key, k * step_s, "tick")
            k += 1

    last_t, a = 0, 0
    while a < len(lines):
        t = lines[a][0]
        b = a
        while b < len(lines) and lines[b][0] == t:
            b += 1
        tick_to(t)       # ticks up to and including t see the state BEFORE this instant's events
        touched = set()
        for j in range(a, b):
            touched.update(apply(lines[j][2]))
        for key in sorted(touched, key=_utf16):
            sample(key, t, "event")
        if touched:
            last_t = t
        a = b
    tick_to(last_t + TAIL_S)
    return {"v": 1, "name": str(head.get("name") or ""), "host": host, "step_s": step_s, "skipped": skipped,
            "roots": roots}
