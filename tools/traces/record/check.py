#!/usr/bin/env python3
"""Recording-level claims for each shipped trace (what the recording was made to PROVE).

This is NOT the state reducer (P2-STATE owns reducers + replayer). It only checks that the data on disk
contains the event shapes each trace is documented to contain, so a re-record that silently lost its point
(e.g. compression did not rotate, the approval never opened) is caught.

    python3 tools/traces/record/check.py [tools/traces/*.jsonl]      # exit 1 on any failed claim
"""
import json
import re
import sys
from pathlib import Path

TRACES = Path(__file__).resolve().parents[1]
PRIVACY = re.compile(r"adam|/home/|api[_-]?key|sk-|token|password", re.I)


def load(path):
    lines = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    return lines[0], lines[1:]


def kinds(body, src=None):
    return [l["kind"] for l in body if src is None or l["src"] == src]


def hooks(body, kind, **payload):
    return [l for l in body if l["src"] == "hook" and l["kind"] == kind and all(l["payload"].get(k) == v for k, v in payload.items())]


def max_concurrent(body):
    """Peak number of TUI owners alive at once, from liveness (first line per lineage root .. its pid_dead)."""
    start, end = {}, {}
    for l in body:
        if l["src"] != "liveness" or not l["lineage_root"]:
            continue
        start.setdefault(l["lineage_root"], l["t"])
        if l["kind"] == "pid_dead":
            end[l["lineage_root"]] = l["t"]
    ev = sorted([(t, 1) for t in start.values()] + [(t, -1) for t in end.values()])
    cur = peak = 0
    for _, d in ev:
        cur += d
        peak = max(peak, cur)
    return peak


def ok_turn(h, b):
    return [bool(hooks(b, "pre_llm_call")), bool(hooks(b, "on_session_end", completed=True)), bool(hooks(b, "pre_tool_call")), bool(hooks(b, "post_tool_call"))]


def ok_clarify(h, b):
    pre = [l["payload"]["tool_call_id"] for l in hooks(b, "pre_tool_call", tool_name="clarify")]
    post = {l["payload"]["tool_call_id"] for l in hooks(b, "post_tool_call", tool_name="clarify")}
    return [len(pre) >= 3, len(set(pre)) == len(pre), set(pre) <= post]  # answered, cancelled, re-asked; every one closed by id


def ok_approval(h, b):
    choices = {l["payload"].get("choice") for l in hooks(b, "post_approval_response")}
    return [len(hooks(b, "pre_approval_request")) >= 2, {"once", "deny"} <= choices]


def ok_tool_error(h, b):
    return [len(hooks(b, "post_tool_call")) >= 2, not hooks(b, "api_request_error"), len(hooks(b, "on_session_end", completed=True)) >= 2]


def ok_401(h, b):
    errs = hooks(b, "api_request_error", status_code=401, retryable=False)
    t_first = errs[0]["t"] if errs else 0
    # no completion signal between the first error and the final /exit teardown (interrupted)
    done = [l for l in b if l["src"] == "hook" and l["t"] > t_first
            and (l["kind"] == "post_llm_call" or (l["kind"] == "on_session_end" and l["payload"].get("completed")))]
    return [len(errs) >= 2, not done]


def ok_retryable(h, b):
    errs = hooks(b, "api_request_error", retryable=True)
    return [len(errs) >= 3, not hooks(b, "post_llm_call"), not hooks(b, "on_session_end", completed=True)]


def ok_kill9(h, b):
    last = b[-1]
    dead = [l for l in b if l["kind"] == "pid_dead"]
    return [last["kind"] == "pid_dead", len(dead) == 1, len(kinds(b, "liveness")) > 3,
            not [l for l in b if l["src"] == "hook" and l["t"] > dead[0]["t"]],
            len(hooks(b, "pre_llm_call")) > len(hooks(b, "on_session_end", completed=True))]  # died mid-turn


def ok_rotate(h, b):
    ids = {l["session"] for l in b if l["src"] == "hook"}
    roots = {l["lineage_root"] for l in b if l["src"] == "hook"}
    return [len(ids) >= 2, len(roots) == 1, None not in roots]


def ok_verify(h, b):
    v = hooks(b, "pre_verify")
    if not v:
        return [False]
    t = v[0]["t"]
    before = [l["t"] for l in hooks(b, "post_tool_call") if l["t"] <= t]
    after = [l["t"] for l in hooks(b, "post_llm_call") if l["t"] >= t]
    return [len(v) == 1, bool(before), bool(after)]


def ok_twenty(h, b):
    roots = {l["lineage_root"] for l in b if l["src"] == "hook"}
    turned = {l["lineage_root"] for l in hooks(b, "pre_llm_call")}
    return [len(roots) == 20, turned == roots, max_concurrent(b) >= 4]


def ok_profiles(h, b):
    seq = [l["profile"] for l in hooks(b, "pre_llm_call")]
    collapsed = [p for i, p in enumerate(seq) if i == 0 or p != seq[i - 1]]
    return [h["profiles"] == ["A", "B"], collapsed[:4] == ["A", "B", "A", "B"],
            not ({l["lineage_root"] for l in b if l["profile"] == "A" and l["lineage_root"]} &
                 {l["lineage_root"] for l in b if l["profile"] == "B" and l["lineage_root"]})]


def ok_d_main(h, b):
    labels = [l["payload"]["label"] for l in b if l["src"] == "desktop.dot"]
    return [labels.count("Needs your input") >= 2, "Session running" in labels, bool([l for l in b if l["kind"] == "message.complete"]),
            any(l["payload"].get("busy") for l in b if l["src"] == "desktop.state"),
            {"clarify"} <= {l["payload"].get("tool_name") for l in b if l["kind"] == "tool.start"}]


def ok_d_error(h, b):
    mc = [l for l in b if l["kind"] == "message.complete"]
    return [bool(mc) and mc[-1]["payload"].get("status") == "error", bool(mc) and "code" in mc[-1]["payload"].get("error_surface", {})]


def ok_d_kill(h, b):
    st = [l["payload"] for l in b if l["src"] == "desktop.state"]
    return [any(s["gateway"] == "closed" and s.get("busy") for s in st), any(s["gateway"] == "open" for s in st[-3:])]


CLAIMS = {
    "turn": ok_turn, "clarify": ok_clarify, "approval": ok_approval, "tool-error": ok_tool_error, "api-error-401": ok_401,
    "api-error-retryable": ok_retryable, "crash-kill9": ok_kill9, "compression-rotate": ok_rotate, "review-verify": ok_verify,
    "twenty-sessions": ok_twenty, "two-profiles": ok_profiles, "desktop-main": ok_d_main, "desktop-error": ok_d_error,
    "desktop-kill": ok_d_kill,
}


def check(path):
    """-> list of failure strings (empty = every claim holds and the file is privacy-clean)."""
    path = Path(path)
    problems = []
    text = path.read_text()
    m = PRIVACY.search(text)
    if m:
        problems.append(f"privacy pattern {m.group(0)!r}")
    head, body = load(path)
    if head.get("src") != "meta" or head.get("v") != 1 or head.get("name") != path.stem:
        problems.append("bad header")
    if [l["t"] for l in body] != sorted(l["t"] for l in body):
        problems.append("not sorted by t")
    claim = CLAIMS.get(path.stem)
    if claim is None:
        problems.append("no claim registered")
    else:
        res = claim(head, body)
        problems += [f"claim #{i} false" for i, r in enumerate(res) if not r]
    return problems


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(str(p) for p in TRACES.glob("*.jsonl"))
    bad = 0
    for f in files:
        p = check(f)
        print(("OK   " if not p else "FAIL ") + Path(f).name + ("" if not p else "  " + "; ".join(p)))
        bad += bool(p)
    sys.exit(1 if bad else 0)
