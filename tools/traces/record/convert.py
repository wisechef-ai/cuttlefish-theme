#!/usr/bin/env python3
"""Raw recorder output -> contract section 4 trace lines (tools/traces/*.jsonl).

    python3 tools/traces/record/convert.py RAW_DIR OUT.jsonl

The plugin repo is PUBLIC, so this converter is a WHITELIST, not a scrubber: a payload field survives
only if it is listed below for its source. Everything else (prompts, tool args, model output, cwd, paths,
usernames, tokens, pids) is never read into the output. As a last line of defence every emitted line is
checked against the privacy pattern and the conversion FAILS CLOSED (ValueError) if anything matches.

Raw layouts (written by record/lib.py and record/desktop.ts):
  TUI      meta.json, hooks-<P>.jsonl (hookdump rows), liveness.jsonl, state-<P>.db (copy of the temp home's state.db)
  desktop  meta.json, events.jsonl, states.jsonl, dots.jsonl (spike-07 shapes, t in epoch ms), state-<P>.db
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

# ----- whitelists (contract section 4). Per source, so a free-text field can never ride in on another source.
HOOK_FIELDS = ("tool_name", "tool_call_id", "session_key", "pattern_key", "completed", "interrupted", "failed",
               "status_code", "retryable", "choice")
# The hooks the reducers consume (contract section 2). Everything else (stream deltas, aux calls, pre_api_request) is dropped.
HOOKS = frozenset({
    "on_session_reset", "on_session_start", "pre_llm_call", "post_llm_call", "on_session_end", "on_session_finalize",
    "pre_tool_call", "post_tool_call", "pre_approval_request", "post_approval_response", "api_request_error", "pre_verify",
})
# desktop gateway event type -> payload extractor
DESKTOP_EVENTS = frozenset({"session.info", "message.start", "message.complete", "tool.start", "tool.complete", "gateway.ready"})
_SCALAR = (str, int, float, bool, type(None))

PRIVACY = re.compile(r"adam|/home/|api[_-]?key|sk-|token|password", re.I)


# ----- lineage
class Lineage:
    """session id -> lineage root, walked through state.db sessions.parent_session_id (read-only)."""

    def __init__(self, db_paths):
        self.parent = {}
        for p in db_paths:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            try:
                for sid, par in con.execute("select id, parent_session_id from sessions"):
                    self.parent[sid] = par or None
            finally:
                con.close()

    def root(self, sid):
        if not sid or sid not in self.parent:
            return None
        seen = set()
        while self.parent.get(sid) and sid not in seen:
            seen.add(sid)
            sid = self.parent[sid]
        return sid


def _lineage(raw: Path):
    return Lineage(sorted(raw.glob("state-*.db")))


# ----- helpers
def _meta(raw: Path):
    return json.loads((raw / "meta.json").read_text())


def _rows(path: Path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _header(m):
    return {"v": 1, "src": "meta", "kind": "trace", "name": m["name"], "host": m["host"], "runtime": m["runtime"],
            "runtime_sha": m["runtime_sha"], "recorded_at": m["recorded_at"], "model": m["model"],
            "profiles": m["profiles"], "notes": m.get("notes", "")}


def _line(t, src, profile, session, lineage_root, kind, payload):
    return {"v": 1, "t": round(t, 3), "src": src, "profile": profile, "session": session or None,
            "lineage_root": lineage_root, "kind": kind, "payload": payload}


def _finish(lines):
    head, body = lines[0], lines[1:]
    body = sorted(enumerate(body), key=lambda p: (p[1]["t"], p[0]))
    out = [head] + [l for _, l in body]
    for l in out:
        s = json.dumps(l, separators=(",", ":"))
        m = PRIVACY.search(s)
        if m:
            raise ValueError(f"privacy gate: {m.group(0)!r} in {s[:160]}")
    return out


def _hook_payload(row):
    ids, keys = row.get("ids", {}), row.get("keys", {})
    out = {}
    for f in HOOK_FIELDS:
        if f in ids:
            out[f] = ids[f]
        elif f in keys and keys[f].get("t") in ("str", "int", "float", "bool", "NoneType") and "v" in keys[f]:
            out[f] = keys[f]["v"]
    return {k: v for k, v in out.items() if isinstance(v, _SCALAR) and v is not None}


# ----- TUI
def convert_tui(raw):
    raw = Path(raw)
    m, lin = _meta(raw), _lineage(raw)
    t0 = m["t0"]
    lines = [_header(m)]
    for p in sorted(raw.glob("hooks-*.jsonl")):
        profile = p.stem.split("-", 1)[1]
        for row in _rows(p):
            hook = row.get("hook")
            if hook not in HOOKS:
                continue
            ids = row.get("ids", {})
            sid = ids.get("session_id") or ids.get("session_key")
            if not sid:
                continue
            lines.append(_line(row["ts"] - t0, "hook", profile, sid, lin.root(sid), hook, _hook_payload(row)))
    for row in _rows(raw / "liveness.jsonl"):
        kind = row["kind"]
        payload = {"bound": bool(row["bound"])} if kind == "binding" else {}
        sid = row.get("session")
        lines.append(_line(row["ts"] - t0, "liveness", row["profile"], sid, lin.root(sid), kind, payload))
    return _finish(lines)


# ----- desktop
def _event_payload(typ, p):
    p = p or {}
    out = {}
    if typ == "session.info" and p.get("stored_session_id"):
        out["stored_session_id"] = p["stored_session_id"]
    elif typ == "message.complete":
        if p.get("status") in ("complete", "error"):
            out["status"] = p["status"]
        code = (p.get("error_surface") or {}).get("code")
        if code:
            out["error_surface"] = {"code": code}
    elif typ in ("tool.start", "tool.complete"):
        if p.get("name"):
            out["tool_name"] = p["name"]
        if p.get("tool_id"):
            out["tool_call_id"] = p["tool_id"]
    return out


def _dot_label(dots: str):
    """'main:Needs your input|side:Session running' -> the one label the reducer reads (needs-input outranks running)."""
    labels = [d.split(":", 1)[1] if ":" in d else d for d in dots.split("|") if d]
    for want in ("Needs your input", "Session running"):
        if want in labels:
            return want
    return labels[0] if labels else ""


def convert_desktop(raw):
    raw = Path(raw)
    m, lin = _meta(raw), _lineage(raw)
    t0, profile = m["t0"], m["profiles"][0]
    ms = lambda v: v / 1000.0 - t0  # noqa: E731
    events = [r for r in _rows(raw / "events.jsonl") if "event" in r]
    states = _rows(raw / "states.jsonl")
    # runtime -> stored id: the only event that carries both is session.info (events for a runtime id with no known mapping stay unmapped)
    rt2stored = {}
    for r in events:
        e = r["event"]
        sp = (e.get("payload") or {}).get("stored_session_id")
        if e.get("type") == "session.info" and sp and e.get("session_id"):
            rt2stored[e["session_id"]] = sp
    for s in states:
        if s.get("focusedSessionId") and s.get("focusedStoredSessionId"):
            rt2stored.setdefault(s["focusedSessionId"], s["focusedStoredSessionId"])
    lines = [_header(m)]
    for r in events:
        e = r["event"]
        typ = e.get("type")
        if typ not in DESKTOP_EVENTS:
            continue
        rt = e.get("session_id") or None
        lines.append(_line(ms(r["t"]), "desktop.event", profile, rt, lin.root(rt2stored.get(rt)), typ,
                           _event_payload(typ, e.get("payload"))))
    last = None
    for s in states:
        busy = s.get("busyBySession") or {}
        sig = (s.get("gateway"), tuple(sorted(busy.items())), s.get("focusedStoredSessionId"))
        if sig == last:
            continue
        last = sig
        if not busy:
            lines.append(_line(ms(s["t"]), "desktop.state", profile, None, None, "state", {"gateway": s.get("gateway")}))
        for rt, b in sorted(busy.items()):
            payload = {"gateway": s.get("gateway"), "busy": bool(b)}
            stored = rt2stored.get(rt)
            if stored:
                payload["stored_session_id"] = stored
            lines.append(_line(ms(s["t"]), "desktop.state", profile, rt, lin.root(stored), "state", payload))
    focus = sorted((s["t"], s["focusedStoredSessionId"]) for s in states if s.get("focusedStoredSessionId"))
    last_label = None
    for d in _rows(raw / "dots.jsonl"):
        label = _dot_label(d.get("dots", ""))
        if label == last_label:
            continue
        last_label = label
        stored = None
        for t, sid in focus:
            if t <= d["t"]:
                stored = sid
        payload = {"label": label}
        if stored:
            payload["stored_session_id"] = stored
        lines.append(_line(ms(d["t"]), "desktop.dot", profile, stored, lin.root(stored), "dot", payload))
    return _finish(lines)


def convert(raw):
    return (convert_desktop if _meta(Path(raw))["host"] == "desktop" else convert_tui)(raw)


def write_trace(lines, out):
    Path(out).write_text("".join(json.dumps(l, separators=(",", ":")) + "\n" for l in lines))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ls = convert(sys.argv[1])
    write_trace(ls, sys.argv[2])
    print(f"{sys.argv[2]}: {len(ls)} lines")
