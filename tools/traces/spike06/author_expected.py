#!/usr/bin/env python3
"""Authoring aid for expected.json. NOT a reducer.

Every state below is typed by hand from the spike 06 receipt (section 1.3 table + prose; times quoted per
trace) and, where the receipt is silent, from CONTRACT section 2 (flagged in `notes`). The only computation here
is expanding index ranges to one state per event and deriving `since` (ts of the event where the labelled
state last changed) from the labels themselves. No fixture is replayed through any reducer.

    python3 author_expected.py [--check]
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
I, W, R, N, F, U = "idle", "working", "review", "needs-you", "fault", "unknown"

# (first_idx, last_idx, state) over the fixture's event indices (see <name>.jsonl, 0-based).
LABELS = {
    "main": {
        "source": "receipt 1.3: working 6.4->31.9 s; clarify 43.2->53.2 s; cancel 58.9->66.2 s, re-ask 68.2 stays open ~66 s",
        "segments": [(0, 1, I), (2, 3, W), (4, 4, I), (5, 8, W), (9, 9, I), (10, 10, W), (11, 11, N), (12, 13, W),
                     (14, 14, I), (15, 15, W), (16, 16, N), (17, 17, W), (18, 18, N), (19, 20, W), (21, 21, I),
                     (22, 23, W), (24, 24, I), (25, 26, W), (27, 28, I), (29, 29, U)],
        "notes": [
            "idx 17 (66.24 s): receipt says the cancelled clarify clears at the cancel and the model re-asks at 68.2 s; the 2 s gap is labelled working (CONTRACT 2: the first clarify's key is removed, second not yet added).",
            "idx 28 (297.92 s): on_session_end{completed:false, interrupted:true} is the real end per the receipt; the window is idle until on_session_finalize (idx 29) -> unknown.",
            "idx 4/9/14/21/24/27: on_session_end per turn -> idle (receipt: 'on_session_end fires at the end of EVERY TURN'; main.jsonl working ends 31.9 s).",
        ],
    },
    "error": {
        "source": "receipt: dead base_url, api_request_error once per attempt (8 in 85 s in the receipt run; this raw log holds 11 within 88 s), no turn-end hook, fault until exit",
        "segments": [(0, 1, I), (2, 2, W), (3, 13, F), (14, 14, F), (15, 15, U)],
        "notes": [
            "The receipt prose says 8 retries; the raw error.jsonl has 11 api_request_error events (idx 3-13). Receipt count is a prose summary of the same run; the artifact is authoritative for the fixture.",
            "idx 14 (93.15 s): on_session_end{completed:false, interrupted:true} at /exit. The receipt does not say whether this clears fault; labelled fault from CONTRACT 2 ('fault is sticky across on_session_end{completed:false}').",
            "idx 15: on_session_finalize -> unknown (receipt: 'on_session_finalize seen' is a synthesised-unknown trigger).",
        ],
    },
    "failed": {
        "source": "receipt: HTTP 401 stub, api_request_error once, no on_session_end/post_llm_call, next user turn starts with a plain pre_llm_call and errors again",
        "segments": [(0, 1, I), (2, 2, W), (3, 3, F), (4, 4, W), (5, 6, F), (7, 7, U)],
        "notes": [
            "idx 3 -> 4: the fault (401) is sticky until the next user turn starts; pre_llm_call (idx 4, 47.05 s) clears it back to working, and the second 401 (idx 5) faults again (receipt: 'errors again').",
            "idx 6 (77.49 s): on_session_end{completed:false} at exit; fault stays sticky per CONTRACT 2 (receipt silent). idx 7 finalize -> unknown.",
        ],
    },
    "approval": {
        "source": "receipt: pre_approval_request when the dialog opens, post_approval_response when answered; sequence pre_tool_call(terminal), pre_approval_request, (user), post_approval_response, post_tool_call",
        "segments": [(0, 1, I), (2, 3, W), (4, 4, N), (5, 7, W), (8, 9, I), (10, 10, U)],
        "notes": [
            "needs-you spans 18.53 s -> 109.58 s (a human sat on the dialog for ~91 s).",
            "idx 9 (113.76 s): on_session_end{completed:false} with no pending key -> idle until finalize (idx 10).",
        ],
    },
    "rotate": {
        "source": "receipt Compression: rotate.jsonl is the IN-PLACE /compress run: id unchanged, nothing else fires; plain turns",
        "segments": [(0, 1, I), (2, 3, W), (4, 4, I), (5, 6, W), (7, 7, I), (8, 9, W), (10, 11, I), (12, 12, U)],
        "notes": [
            "Despite its name this artifact never rotates the id (one session id throughout); the rotating case is rotate_lineage.jsonl.",
        ],
    },
    "verify_approval": {
        "source": "receipt: pre_verify 21.6 s (review, ~100 ms) then post_llm_call/on_session_end; approval 25.9 -> 32.2 s",
        "segments": [(0, 1, I), (2, 4, W), (5, 5, R), (6, 6, W), (7, 7, I), (8, 9, W), (10, 10, N), (11, 13, W),
                     (14, 15, I), (16, 16, U)],
        "notes": [
            "review lasts idx 5 (21.59 s) -> idx 6 (21.68 s) = 90 ms, matching the receipt's '~100 ms'.",
            "idx 6: the receipt table says review is cleared by post_llm_call; CONTRACT 2 maps post_llm_call from review to working (not idle). Labelled working; idle follows at on_session_end (idx 7, 21.70 s).",
            "idx 11/12 (32.22 s): post_approval_response and post_tool_call arrive in the same instant; both labelled working.",
        ],
    },
    "approval_chain": {
        "source": "receipt 'Approval' + lineage run (spike 05/06 single-TUI): 18 sequential approvals over 6 turns, each pre_approval_request..post_approval_response = needs-you",
        "segments": [(0, 1, I), (2, 6, W), (7, 7, N), (8, 10, W), (11, 11, I), (12, 13, W), (14, 14, N), (15, 17, W),
                     (18, 18, N), (19, 21, W), (22, 22, N), (23, 25, W), (26, 26, N), (27, 29, W), (30, 30, N),
                     (31, 33, W), (34, 34, N), (35, 37, W), (38, 38, N), (39, 41, W), (42, 42, N), (43, 45, W),
                     (46, 46, N), (47, 49, W), (50, 50, N), (51, 53, W), (54, 54, N), (55, 57, W), (58, 58, I),
                     (59, 60, W), (61, 61, N), (62, 64, W), (65, 65, N), (66, 68, W), (69, 69, I), (70, 71, W),
                     (72, 72, N), (73, 75, W), (76, 76, I), (77, 78, W), (79, 79, N), (80, 82, W), (83, 83, N),
                     (84, 86, W), (87, 87, N), (88, 88, I), (89, 89, U)],
        "notes": [
            "idx 87 (pre_approval_request c18) is never answered: the run was stopped (agent_loop_stopped, not a subscribed hook). The receipt does not say what a session end does to a still-open dialog; labelled idle at idx 88 from CONTRACT 2 (on_session_end clears pending). A UI may disagree; this is the one place the contract, not the receipt, decides.",
            "Approvals are stacked in a single turn (idx 12-58): after each post_approval_response the state returns to working, not idle (no turn end yet).",
        ],
    },
    "rotate_lineage": {
        "source": "receipt Compression/Ids: rotating compression, child id appears unannounced on the next pre_llm_call (115737_78f947 -> 120603_0bed33), on_session_start NOT re-fired",
        "segments": [(0, 0, I), (1, 2, W), (3, 3, I), (4, 5, W), (6, 6, I), (7, 8, W), (9, 9, I), (10, 11, W), (12, 12, I),
                     (13, 13, I), (14, 14, U)],
        "notes": [
            "S2 (child) appears first at idx 10 (pre_llm_call) with no reset/start hook, exactly as the receipt describes; lineage.json maps S2 -> S1 (state.db parent link). Both ids belong to ONE lineage root (S1), so the reducer input is the whole file in arrival order.",
            "idx 13: on_session_end{completed:false} then idx 14 finalize carry the child id S2.",
        ],
    },
}


def expand(name, trace_path):
    ev = [json.loads(l) for l in open(trace_path)]
    states = [None] * len(ev)
    for a, b, s in LABELS[name]["segments"]:
        for i in range(a, b + 1):
            assert states[i] is None, (name, i, "labelled twice")
            states[i] = s
    assert None not in states, (name, [i for i, s in enumerate(states) if s is None])
    out, prev, since = [], None, None
    for e, s in zip(ev, states):
        if s != prev:
            since, prev = e["ts"], s
        out.append({"hook": e["hook"], "state": s, "since": since})
    return out


def build():
    doc = {"schema": "cf2909.spike06-expected/1", "states": [I, W, R, N, F, U], "traces": {}}
    for name, spec in LABELS.items():
        doc["traces"][name] = {"source": spec["source"], "notes": spec["notes"],
                               "after_each_event": expand(name, HERE / (name + ".jsonl"))}
    return json.dumps(doc, indent=1) + "\n"


if __name__ == "__main__":
    text, path = build(), HERE / "expected.json"
    if "--check" in sys.argv:
        sys.exit(0 if path.exists() and path.read_text() == text else 1)
    path.write_text(text)
    print("wrote", path.name)
