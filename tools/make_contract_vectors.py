#!/usr/bin/env python3
"""Write (or --check) the cf2909 contract golden vectors from the Python reference.

    python tools/make_contract_vectors.py [--check] [--out-dir DIR]

Outputs identity-vectors.json and state-vectors.json (default dir: packages/core/spec). Deterministic:
fixed seed, no clock, sorted/stable JSON. --check exits 1 if any file differs or is missing. The TS core
(P2) is tested against these files; change the CONTRACT, bump the schema suffix, regenerate in the same PR.
"""
import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "packages" / "core" / "spec"


def _load(name):
    spec = importlib.util.spec_from_file_location("_cf_dom_" + name, REPO / "python" / "domain" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A, R = _load("allocator"), _load("reducer")


# ---------------------------------------------------------------- identity
def identity_cases():
    rnd = random.Random(2909)
    grid = [A.cand(k) for k in range(A.GRID)]
    odd = ["", " ", "abc", "日本語のセッション", "ünïcödé-ß", "😀🐙" * 3, "a\u0000b", "tab\there", "line\nbreak",
           "e\u0301 (combining)", "العربية", "x" * 300, "../../etc/passwd", "a/b\\c", "\u202eRTL", "UPPER lower 123",
           "20261015_120000_ab12cd"]
    roots = odd + [f"20261015_{rnd.randrange(10**6):06d}_{rnd.getrandbits(24):06x}" for _ in range(60)]
    cases = []

    def add(root, peers):
        a = A.allocate(root, peers)
        cases.append({"lineage_root": root, "peers_cd": peers, "expected_hue_cd": a.hue_cd,
                      "expected_base": a.base, "digest_hex": a.digest_hex})

    for r in roots:                                   # alone
        add(r, [])
    for n in (1, 2, 3):                               # 1-3 peers
        for r in roots[: 30 + 10 * n]:
            add(r, [rnd.choice(grid) for _ in range(n)])
    for r in roots:                                   # crowded 8-24 peers
        n = rnd.randint(8, 24)
        add(r, [rnd.choice(grid) for _ in range(n)])
    for r in roots[:40]:                              # duplicate peers
        p = rnd.choice(grid)
        add(r, [p, p, p] + [rnd.choice(grid) for _ in range(rnd.randint(0, 4))])
    for r in roots[:20]:                              # evenly occupied arc: only the leftovers remain
        free = rnd.sample(range(A.GRID), 3)
        add(r, [grid[k] for k in range(A.GRID) if k not in free])
    for r in roots[:20]:                              # peers off the grid / near the 0/360 wrap
        add(r, [rnd.choice([0, 1, 35999, 35000, 17999, 18000, 10999, 34001, 12345])] + [rnd.choice(grid)])
    return {"schema": "cf2909.identity-vectors/1", "contract": "cf2909.identity/1", "cases": cases}


# ---------------------------------------------------------------- state
def _ev(hook, ts, sid="s1", tool=None, call=None, turn=None, completed=None):
    return {"hook": hook, "ts": ts, "session_id": sid, "tool_name": tool, "tool_call_id": call,
            "turn_id": turn, "completed": completed}


def state_sequences():
    """Hand-built sequences: (name, [events]). Timestamps are exact binary fractions."""
    E = _ev
    seqs = []

    def add(name, *events):
        seqs.append((name, [dict(e, ts=float(10 + i)) for i, e in enumerate(events)]))

    def clar_pre(c, **k): return E("pre_tool_call", 0, tool="clarify", call=c, **k)
    def clar_post(c, **k): return E("post_tool_call", 0, tool="clarify", call=c, **k)

    # one per table row
    add("row-reset-from-busy", E("pre_llm_call", 0), clar_pre("c1"), E("api_request_error", 0), E("on_session_reset", 0))
    add("row-reset-after-finalize", E("on_session_finalize", 0), E("on_session_reset", 0))
    add("row-start-only", E("on_session_start", 0))
    add("row-start-unfinalizes", E("on_session_finalize", 0), E("on_session_start", 0))
    add("row-pre-llm-working", E("pre_llm_call", 0))
    add("row-pre-llm-clears-pending-and-fault", clar_pre("c1"), E("api_request_error", 0), E("pre_llm_call", 0))
    add("row-pre-llm-unfinalizes", E("on_session_finalize", 0), E("pre_llm_call", 0))
    add("row-pre-verify-review", E("pre_llm_call", 0), E("pre_verify", 0))
    add("row-pre-verify-from-idle-ignored", E("pre_verify", 0))
    add("row-pre-verify-twice", E("pre_llm_call", 0), E("pre_verify", 0), E("pre_verify", 0))
    add("row-post-llm-review-to-working", E("pre_llm_call", 0), E("pre_verify", 0), E("post_llm_call", 0))
    add("row-post-llm-clears-fault", E("pre_llm_call", 0), E("api_request_error", 0), E("post_llm_call", 0))
    add("row-post-llm-idle-noop", E("post_llm_call", 0))
    add("row-session-end-idle", E("pre_llm_call", 0), E("on_session_end", 0, completed=True))
    add("row-session-end-completed-clears-fault", E("pre_llm_call", 0), E("api_request_error", 0),
        E("on_session_end", 0, completed=True))
    add("row-session-end-failed-keeps-fault", E("pre_llm_call", 0), E("api_request_error", 0),
        E("on_session_end", 0, completed=False))
    add("row-session-end-null-completed-keeps-fault", E("api_request_error", 0), E("on_session_end", 0))
    add("row-session-end-drops-pending", clar_pre("c1"), E("on_session_end", 0, completed=False))
    add("row-clarify-open-close", E("pre_llm_call", 0), clar_pre("c1"), clar_post("c1"))
    add("row-clarify-close-wrong-id", clar_pre("c1"), clar_post("c2"))
    add("row-clarify-duplicate-pre", clar_pre("c1"), clar_pre("c1"), clar_post("c1"))
    add("row-clarify-null-call-id", E("pre_tool_call", 0, tool="clarify"), E("post_tool_call", 0, tool="clarify"))
    add("row-other-tool-ignored", E("pre_llm_call", 0), E("pre_tool_call", 0, tool="terminal", call="t1"),
        E("post_tool_call", 0, tool="terminal", call="t1"))
    add("row-tool-null-name-ignored", E("pre_tool_call", 0), E("post_tool_call", 0))
    add("row-approval-by-tool-call-id", E("pre_approval_request", 0, call="a1", turn="T1"),
        E("post_approval_response", 0, call="a1", turn="T1"))
    add("row-approval-by-turn-id", E("pre_approval_request", 0, turn="T1"), E("post_approval_response", 0, turn="T1"))
    add("row-approval-empty-key", E("pre_approval_request", 0), E("post_approval_response", 0))
    add("row-approval-mismatched-response", E("pre_approval_request", 0, call="a1"),
        E("post_approval_response", 0, call="a2"))
    add("row-approval-prefers-call-id-over-turn", E("pre_approval_request", 0, call="a1", turn="T1"),
        E("post_approval_response", 0, turn="T1"), E("post_approval_response", 0, call="a1", turn="other"))
    add("row-api-error-fault", E("pre_llm_call", 0), E("api_request_error", 0))
    add("row-finalize-unknown", E("pre_llm_call", 0), E("on_session_finalize", 0))
    add("row-ignored-hooks", E("pre_llm_call", 0), E("on_stream_delta", 0), E("pre_api_request", 0),
        E("transform_terminal_output", 0))
    # precedence overlaps
    add("prec-needs-you-over-fault", E("pre_llm_call", 0), E("api_request_error", 0), clar_pre("c1"), clar_post("c1"))
    add("prec-fault-over-working", E("pre_llm_call", 0), E("api_request_error", 0), E("pre_llm_call", 0))
    add("prec-fault-over-review", E("pre_llm_call", 0), E("pre_verify", 0), E("api_request_error", 0),
        E("post_llm_call", 0))
    add("prec-needs-you-over-review", E("pre_llm_call", 0), E("pre_verify", 0), clar_pre("c1"), clar_post("c1"))
    add("prec-finalize-over-needs-you", clar_pre("c1"), E("on_session_finalize", 0))
    add("prec-finalize-over-fault", E("api_request_error", 0), E("on_session_finalize", 0))
    add("prec-finalize-then-events-stay-unknown", E("pre_llm_call", 0), E("on_session_finalize", 0),
        E("post_llm_call", 0), E("pre_verify", 0), E("api_request_error", 0))
    add("prec-clarify-and-approval-both-open", clar_pre("k"), E("pre_approval_request", 0, call="k"),
        clar_post("k"), E("post_approval_response", 0, call="k"))
    add("prec-two-clarifies", clar_pre("a"), clar_pre("b"), clar_post("a"), clar_post("b"))
    add("prec-approval-during-working-then-answered", E("pre_llm_call", 0), E("pre_approval_request", 0, call="a1"),
        E("post_approval_response", 0, call="a1"), E("on_session_end", 0, completed=True))
    # scenarios called out by the task
    add("reask-cancelled-clarify-new-id", E("pre_llm_call", 0), clar_pre("c1"), clar_post("c1"), clar_pre("c2"),
        clar_post("c2"), E("post_llm_call", 0), E("on_session_end", 0, completed=True))
    add("reask-cancelled-clarify-same-id-never-sticks", E("pre_llm_call", 0), clar_pre("c1"), clar_post("c1"),
        clar_pre("c1"), clar_post("c1"))
    add("fault-401-no-end-hook-sticky", E("on_session_reset", 0), E("pre_llm_call", 0),
        E("api_request_error", 0, ), E("pre_llm_call", 0), E("api_request_error", 0))
    add("fault-401-then-success", E("pre_llm_call", 0), E("api_request_error", 0), E("pre_llm_call", 0),
        E("post_llm_call", 0), E("on_session_end", 0, completed=True))
    add("fault-retries-interleaved", E("pre_llm_call", 0), E("api_request_error", 0), E("api_request_error", 0),
        E("api_request_error", 0), E("post_llm_call", 0))
    add("rotation-id-changes-same-lineage", E("on_session_reset", 0, sid="parent"), E("pre_llm_call", 0, sid="parent"),
        E("on_session_end", 0, sid="parent", completed=True), E("pre_llm_call", 0, sid="child"),
        E("pre_tool_call", 0, sid="child", tool="clarify", call="c1"),
        E("post_tool_call", 0, sid="child", tool="clarify", call="c1"),
        E("on_session_end", 0, sid="child", completed=True))
    add("rotation-mid-clarify", E("pre_llm_call", 0, sid="p"),
        E("pre_tool_call", 0, sid="p", tool="clarify", call="c1"),
        E("post_tool_call", 0, sid="c", tool="clarify", call="c1"))
    add("finalize-then-new-window-reset", E("pre_llm_call", 0), E("on_session_end", 0, completed=True),
        E("on_session_finalize", 0), E("on_session_reset", 0, sid="s2"), E("pre_llm_call", 0, sid="s2"))
    add("reset-mid-turn", E("pre_llm_call", 0), E("pre_verify", 0), E("on_session_reset", 0))
    add("full-coding-turn", E("on_session_reset", 0), E("on_session_start", 0), E("pre_llm_call", 0),
        E("pre_tool_call", 0, tool="write_file", call="w1"), E("post_tool_call", 0, tool="write_file", call="w1"),
        E("pre_verify", 0), E("post_llm_call", 0), E("on_session_end", 0, completed=True),
        E("on_session_finalize", 0))
    add("long-session-many-turns", *sum(([E("pre_llm_call", 0), E("post_llm_call", 0),
                                          E("on_session_end", 0, completed=True)] for _ in range(6)), []))
    return seqs


def state_cases():
    cases = []
    for name, events in state_sequences():
        full = []
        for e in events:
            full.append({k: e[k] for k in R.EVENT_KEYS})
        states, _ = R.fold(full)
        cases.append({"name": name, "events": full, "expected_states_after_each_event": states})
    return {"schema": "cf2909.state-vectors/1", "contract": "cf2909.state/1",
            "note": "since = ts of the event that last changed the output state; before any change it is the first event's ts",
            "cases": cases}


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=True, allow_nan=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the files on disk differ from the reference")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    outputs = {"identity-vectors.json": render(identity_cases()), "state-vectors.json": render(state_cases())}
    bad = 0
    for name, text in outputs.items():
        path = args.out_dir / name
        if args.check:
            have = path.read_text(encoding="utf-8") if path.exists() else None
            if have != text:
                print(f"DRIFT: {path} {'missing' if have is None else 'differs from the Python reference'}")
                bad += 1
            else:
                print(f"ok: {path}")
        else:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
