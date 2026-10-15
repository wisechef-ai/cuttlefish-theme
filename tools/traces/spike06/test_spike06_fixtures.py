"""Static checks on the spike 06 replay fixtures. Deliberately imports NO reducer: the reducer replay test
(fixture -> state, compared with expected.json) is wired by the lead at integration."""
import json
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
NAMES = ["main", "error", "failed", "approval", "rotate", "verify_approval", "approval_chain", "rotate_lineage"]
KEYS = {"hook", "ts", "session_id", "tool_name", "tool_call_id", "turn_id", "completed"}
SUBSCRIBED = {
    "on_session_reset", "on_session_start", "pre_llm_call", "pre_verify", "post_llm_call", "on_session_end",
    "pre_tool_call", "post_tool_call", "pre_approval_request", "post_approval_response", "api_request_error",
    "on_session_finalize",
}
STATES = {"idle", "working", "review", "needs-you", "fault", "unknown"}
FORBIDDEN = {"user" + "_message", "args", "command", "conversation_history", "error", "model", "base_url", "paths",
             "changed_paths", "final_response", "request", "description", "pattern_key", "session_key", "task_id",
             "api_request_id", "pid", "keys", "ids"}
SID = re.compile(r"^S[1-9][0-9]*$")


def events(name):
    return [json.loads(l) for l in (HERE / (name + ".jsonl")).read_text().splitlines()]


def walk_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from walk_strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk_strings(v)


EXPECTED = json.loads((HERE / "expected.json").read_text())
LINEAGE = json.loads((HERE / "lineage.json").read_text())


def test_no_stray_fixture_files():
    assert sorted(p.stem for p in HERE.glob("*.jsonl")) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_shape_and_leak_guard(name):
    ev = events(name)
    assert ev, "empty fixture"
    for e in ev:
        assert set(e) == KEYS and not (set(e) & FORBIDDEN)
        assert e["hook"] in SUBSCRIBED
        assert isinstance(e["ts"], (int, float)) and not isinstance(e["ts"], bool)
        assert e["session_id"] is None or SID.match(e["session_id"])
        assert e["completed"] is None or isinstance(e["completed"], bool)
        assert (e["completed"] is not None) == (e["hook"] == "on_session_end")
        assert (e["tool_name"] is not None) == (e["hook"] in ("pre_tool_call", "post_tool_call"))
        for s in walk_strings(e):
            assert len(s) <= 80, "string too long (possible leak): %r" % s[:20]


@pytest.mark.parametrize("name", NAMES)
def test_ts_rebased_and_monotonic(name):
    ts = [e["ts"] for e in events(name)]
    assert ts[0] == 0.0
    assert ts == sorted(ts)


@pytest.mark.parametrize("name", NAMES)
def test_expected_one_state_per_event(name):
    ev, exp = events(name), EXPECTED["traces"][name]["after_each_event"]
    assert len(exp) == len(ev)
    for e, x in zip(ev, exp):
        assert x["hook"] == e["hook"]
        assert x["state"] in STATES
        assert x["since"] <= e["ts"]
    # `since` moves exactly when the labelled state changes
    prev, since = None, None
    for e, x in zip(ev, exp):
        if x["state"] != prev:
            prev, since = x["state"], e["ts"]
        assert x["since"] == since


def test_expected_has_no_extra_traces_and_notes():
    assert sorted(EXPECTED["traces"]) == sorted(NAMES)
    for t in EXPECTED["traces"].values():
        assert t["source"] and isinstance(t["notes"], list)


def test_lineage_maps_child_to_parent():
    assert sorted(LINEAGE) == sorted(NAMES)
    for name in NAMES:
        ids = {e["session_id"] for e in events(name) if e["session_id"]}
        for child, parent in LINEAGE[name].items():
            assert child in ids and parent in ids and child != parent
    assert LINEAGE["rotate_lineage"] == {"S2": "S1"}
    # a rotation is only visible when the stream carries two ids; every other trace carries exactly one
    for name in NAMES:
        n = len({e["session_id"] for e in events(name) if e["session_id"]})
        assert n == (2 if name == "rotate_lineage" else 1)


def test_every_non_unknown_state_covered():
    seen = {x["state"] for t in EXPECTED["traces"].values() for x in t["after_each_event"]}
    assert seen == STATES


def test_end_of_every_trace_is_finalized_unknown():
    for name in NAMES:
        assert events(name)[-1]["hook"] == "on_session_finalize"
        assert EXPECTED["traces"][name]["after_each_event"][-1]["state"] == "unknown"
