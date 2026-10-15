#!/usr/bin/env python3
"""Spike 06 raw hook logs -> public, privacy-scrubbed CONTRACT section 2 replay fixtures.

    python3 convert.py [--src DIR] [--check]

DIR is the directory holding the spike 06 raw artifacts (main.jsonl, ...); it comes from --src or the
CF_SPIKE06_DIR environment variable and is never hard-wired. Without --check the fixtures and lineage.json are
(re)written next to this file. With --check they are rebuilt in memory and compared with the committed copies
(exit 1 on drift).

Kept per event (CONTRACT section 2): hook, ts (rebased: first event 0.0), session_id, tool_name, tool_call_id,
turn_id, completed. Everything else in the raw payloads (the user prompt, args, command, conversation_history, error
text, model, base_url, paths, ...) is never read into the output.
"""
import argparse, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The hooks CONTRACT section 2 reduces over. on_stream_* and everything else is dropped.
SUBSCRIBED = (
    "on_session_reset", "on_session_start", "pre_llm_call", "pre_verify", "post_llm_call", "on_session_end",
    "pre_tool_call", "post_tool_call", "pre_approval_request", "post_approval_response", "api_request_error",
    "on_session_finalize",
)
TOOL_HOOKS = ("pre_tool_call", "post_tool_call")
# fixture name -> (raw artifact, optional selection). A selection cuts one process's contiguous run out of a
# multi-run raw log: pid, plus optionally the nth (0-based) occurrence of (hook, session-suffix) to start at.
SOURCES = {
    "main": ("main.jsonl", {}),
    "error": ("error.jsonl", {}),
    "approval": ("approval.jsonl", {}),
    "rotate": ("rotate.jsonl", {}),
    "verify_approval": ("verify_approval.jsonl", {}),
    "failed": ("failed.jsonl", {}),
    # lineage-hooks.jsonl concatenates several runs. pid 267723 is the single-TUI run (13 sequential approvals).
    "approval_chain": ("lineage-hooks.jsonl", {"pid": 267723}),
    # pid 283875, from the second on_session_reset of ...78f947 (after the b06240 window finalized): three turns
    # in 78f947, then the next turn arrives under the unannounced child id ...0bed33 (rotating compression).
    "rotate_lineage": ("lineage-hooks.jsonl", {"pid": 283875, "start": ("on_session_reset", "78f947", 1)}),
}
# state.db would say sessions.parent_session_id(child) = parent. Only rotate_lineage has a real rotation: the
# receipt (section "Compression") gives 115737_78f947 -> 120603_0bed33 and lineage-hooks.jsonl shows both ids.
ROTATIONS = {"rotate_lineage": [("120603_0bed33", "115737_78f947")]}


def _v(d, key):
    x = d.get("keys", {}).get(key)
    return x.get("v") if isinstance(x, dict) else None


def convert(raw_path, sel):
    rows = []
    for line in open(raw_path, encoding="utf-8"):
        d = json.loads(line)
        if d.get("hook") not in SUBSCRIBED:
            continue
        if "pid" in sel and d.get("pid") != sel["pid"]:
            continue
        rows.append(d)
    if "start" in sel:
        hook, suffix, nth = sel["start"]
        hits = [i for i, d in enumerate(rows) if d["hook"] == hook and (_v(d, "session_id") or "").endswith(suffix)]
        rows = rows[hits[nth]:]
    t0 = rows[0]["ts"]
    sids, tcs, turns, rawsid = {}, {}, {}, {}

    def label(table, raw, fmt):
        if raw in (None, ""):
            return None
        return table.setdefault(raw, fmt(len(table) + 1))

    out = []
    for d in rows:
        h = d["hook"]
        sid = _v(d, "session_id")
        s = label(sids, sid, "S{}".format)
        if sid:
            rawsid[sid] = s
        turn = _v(d, "turn_id")
        if turn:  # "<sid>:<sid>:<hex>" -> keep only the per-turn hex, prefixed by the file-local session label
            parts = turn.split(":")
            turn = "{}:{}".format(rawsid.get(parts[0], "S?"), label(turns, parts[-1], "t{}".format))
        tool = _v(d, "tool_name") if h in TOOL_HOOKS else None
        comp = _v(d, "completed") if h == "on_session_end" else None
        out.append({
            "hook": h, "ts": round(d["ts"] - t0, 2), "session_id": s, "tool_name": tool or None,
            "tool_call_id": label(tcs, _v(d, "tool_call_id"), "c{}".format),
            "turn_id": turn, "completed": comp,
        })
    return out, sids


def build(src):
    files, lineage = {}, {}
    for name, (art, sel) in SOURCES.items():
        out, sids = convert(Path(src) / art, sel)
        files[name] = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in out)
        links = {}
        for child, parent in ROTATIONS.get(name, []):
            c = next(v for k, v in sids.items() if k.endswith(child))
            p = next(v for k, v in sids.items() if k.endswith(parent))
            links[c] = p
        lineage[name] = links
    files["lineage"] = json.dumps(lineage, indent=2, sort_keys=True) + "\n"
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=os.environ.get("CF_SPIKE06_DIR"), help="dir with the raw spike 06 *.jsonl")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if not a.src:
        ap.error("raw artifact dir required: --src DIR or CF_SPIKE06_DIR")
    files = build(a.src)
    bad = 0
    for name, text in files.items():
        path = HERE / ("lineage.json" if name == "lineage" else name + ".jsonl")
        if a.check:
            if not path.exists() or path.read_text() != text:
                print("DRIFT", path.name, file=sys.stderr)
                bad += 1
        else:
            path.write_text(text)
            print("wrote", path.name, text.count("\n"), "lines")
    if a.check:
        print("check:", "FAIL" if bad else "ok", len(files), "files")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
