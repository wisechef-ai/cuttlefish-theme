"""The shipped traces in tools/traces/ must contain what each one was recorded to prove, and stay public-safe.

Recording-level claims only (tools/traces/record/check.py). The state reducers / replayer are P2-STATE's.
"""
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRACES = ROOT / "tools" / "traces"
_spec = importlib.util.spec_from_file_location("trace_check", TRACES / "record" / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

REQUIRED = ["turn", "clarify", "approval", "tool-error", "api-error-401", "api-error-retryable", "crash-kill9",
            "compression-rotate", "review-verify", "twenty-sessions", "two-profiles",
            "desktop-main", "desktop-error", "desktop-kill"]
WHITELIST = {"tool_name", "tool_call_id", "session_key", "pattern_key", "completed", "interrupted", "failed", "status_code",
             "retryable", "choice", "status", "error_surface", "stored_session_id", "focused_session_id", "focused_stored_session_id", "gateway", "busy", "label", "bound"}


def test_the_required_trace_set_is_shipped():
    assert sorted(p.stem for p in TRACES.glob("*.jsonl")) == sorted(REQUIRED)


@pytest.mark.parametrize("name", REQUIRED)
def test_trace_proves_what_it_was_recorded_for(name):
    assert check.check(TRACES / f"{name}.jsonl") == []


@pytest.mark.parametrize("name", REQUIRED)
def test_trace_payloads_are_whitelisted_and_header_is_pinned(name):
    head, body = check.load(TRACES / f"{name}.jsonl")
    assert head["runtime"] == "upstream" and re.fullmatch(r"[0-9a-f]{11}", head["runtime_sha"])
    assert head["model"] == "custom:qwen38-local"
    assert head["host"] == ("desktop" if name.startswith("desktop") else "tui")
    for l in body:
        assert l["v"] == 1 and set(l["payload"]) <= WHITELIST, l


def test_a_trace_that_lost_its_point_fails_the_check(tmp_path):
    # control: a recording whose content is a different scenario's must NOT pass under this name
    wrong = tmp_path / "compression-rotate.jsonl"
    shutil.copy(TRACES / "turn.jsonl", wrong)
    wrong.write_text(wrong.read_text().replace('"name":"turn"', '"name":"compression-rotate"', 1))
    assert check.check(wrong) != []


def test_privacy_pattern_matches_nothing_in_any_shipped_trace():
    pat = re.compile(r"adam|/home/|api[_-]?key|sk-|token|password", re.I)
    assert [p.name for p in TRACES.glob("*.jsonl") if pat.search(p.read_text())] == []
    for p in TRACES.glob("*.jsonl"):
        for line in p.read_text().splitlines():
            json.loads(line)
