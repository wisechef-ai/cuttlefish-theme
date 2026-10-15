"""Behaviour contract for tools/traces/record/convert.py (P23 contract section 4).

The plugin repo is PUBLIC: a recorded trace may carry ONLY the whitelisted payload fields.
Every test feeds raw recorder output through the converter and inspects the emitted trace lines.
"""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("trace_convert", ROOT / "tools" / "traces" / "record" / "convert.py")
convert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert)

WHITELIST = {
    "tool_name", "tool_call_id", "session_key", "pattern_key", "completed", "interrupted", "failed",
    "status_code", "retryable", "choice", "status", "error_surface", "stored_session_id", "focused_session_id", "focused_stored_session_id", "gateway",
    "busy", "label", "bound",
}
SECRET_PROMPT = "please delete /home/adam/secrets and use api_key sk-abc123"


def hook_row(hook, ts, session="S1", ids=None, keys=None):
    base = {"session_id": session}
    base.update(ids or {})
    return {"ts": ts, "seq": 1, "pid": 99, "hook": hook, "keys": keys or {}, "env_active_file": "/tmp/x.json", "ids": base}


def make_raw(tmp_path, hooks, liveness=(), meta=None, sessions=(("S1", None),)):
    raw = tmp_path / "raw"
    raw.mkdir()
    m = {"name": "unit", "host": "tui", "profiles": ["A"], "t0": 1000.0, "recorded_at": "2026-10-15T00:00:00Z",
         "model": "custom:qwen38-local", "runtime": "upstream", "runtime_sha": "f42f579cf8b", "notes": "unit"}
    m.update(meta or {})
    (raw / "meta.json").write_text(json.dumps(m))
    (raw / "hooks-A.jsonl").write_text("".join(json.dumps(r) + "\n" for r in hooks))
    (raw / "liveness.jsonl").write_text("".join(json.dumps(r) + "\n" for r in liveness))
    db = sqlite3.connect(raw / "state-A.db")
    db.execute("create table sessions (id text primary key, parent_session_id text)")
    db.executemany("insert into sessions values (?,?)", list(sessions))
    db.commit()
    db.close()
    return raw


def test_prompt_args_and_paths_never_reach_the_trace(tmp_path):
    dirty = hook_row(
        "pre_tool_call", 1001.0,
        ids={"tool_name": "terminal", "tool_call_id": "call_1", "cwd": "/home/adam/proj"},
        keys={
            "args": {"t": "dict", "keys": ["command"]},
            "user_message": {"t": "str", "v": SECRET_PROMPT},
            "command": {"t": "str", "v": "rm -rf /home/adam/x"},
            "tool_name": {"t": "str", "v": "terminal"},
        },
    )
    dirty["ids"]["user_message"] = SECRET_PROMPT
    dirty["ids"]["args"] = "/home/adam/x"
    lines = convert.convert_tui(make_raw(tmp_path, [dirty]))
    events = [l for l in lines if l["src"] == "hook"]
    assert len(events) == 1
    assert events[0]["payload"] == {"tool_name": "terminal", "tool_call_id": "call_1"}
    blob = json.dumps(lines)
    for leak in ("adam", "/home/", "sk-abc123", "rm -rf", "api_key"):
        assert leak not in blob


def test_every_payload_key_is_whitelisted(tmp_path):
    rows = [
        hook_row("api_request_error", 1001.0, ids={"status_code": 401},
                 keys={"retryable": {"t": "bool", "v": False}, "error": {"t": "str", "v": "boom /home/adam"},
                       "request": {"t": "dict", "keys": ["a"]}}),
        hook_row("post_approval_response", 1002.0, ids={"choice": "deny", "session_key": "S1", "pattern_key": "recursive delete",
                                                       "tool_call_id": "c2", "decided_by": "user"}),
        hook_row("on_session_end", 1003.0, ids={"completed": True, "failed": False, "interrupted": False,
                                                "turn_exit_reason": "text_response", "model": "m"}),
    ]
    lines = convert.convert_tui(make_raw(tmp_path, rows))
    for l in lines:
        assert set(l.get("payload", {})) <= WHITELIST, l
    err = next(l for l in lines if l["kind"] == "api_request_error")
    assert err["payload"] == {"status_code": 401, "retryable": False}


def test_fail_closed_if_a_whitelisted_value_carries_a_secret(tmp_path):
    row = hook_row("pre_approval_request", 1001.0, ids={"pattern_key": "delete in /home/adam/root", "session_key": "S1"})
    with pytest.raises(ValueError, match="privacy"):
        convert.convert_tui(make_raw(tmp_path, [row]))


def test_lineage_root_walks_parent_chain_in_state_db(tmp_path):
    rows = [hook_row("pre_llm_call", 1001.0, session="C3")]
    raw = make_raw(tmp_path, rows, sessions=(("R", None), ("C2", "R"), ("C3", "C2")))
    (ev,) = [l for l in convert.convert_tui(raw) if l["src"] == "hook"]
    assert ev["session"] == "C3" and ev["lineage_root"] == "R"


def test_unknown_session_has_null_lineage_root(tmp_path):
    rows = [hook_row("pre_llm_call", 1001.0, session="GHOST")]
    (ev,) = [l for l in convert.convert_tui(make_raw(tmp_path, rows)) if l["src"] == "hook"]
    assert ev["lineage_root"] is None


def test_header_first_events_sorted_t_relative_and_empty_session_dropped(tmp_path):
    rows = [
        hook_row("on_session_end", 1005.5, ids={"completed": True}),
        hook_row("pre_llm_call", 1001.25),
        hook_row("pre_api_request", 1002.0),          # not in the reducer vocabulary
        hook_row("pre_auxiliary_call", 1003.0, session=""),
    ]
    lines = convert.convert_tui(make_raw(tmp_path, rows))
    head = lines[0]
    assert head["src"] == "meta" and head["kind"] == "trace" and head["v"] == 1
    assert head["name"] == "unit" and head["host"] == "tui" and head["runtime_sha"] == "f42f579cf8b"
    assert [l["kind"] for l in lines[1:]] == ["pre_llm_call", "on_session_end"]
    assert [l["t"] for l in lines[1:]] == [1.25, 5.5]


def test_liveness_lines_heartbeat_pid_dead_binding(tmp_path):
    live = [
        {"ts": 1000.5, "profile": "A", "kind": "binding", "session": "S1", "bound": True},
        {"ts": 1005.5, "profile": "A", "kind": "heartbeat", "session": "S1"},
        {"ts": 1010.5, "profile": "A", "kind": "pid_dead", "session": "S1", "pid": 4242},
    ]
    lines = convert.convert_tui(make_raw(tmp_path, [], liveness=live))
    lv = [l for l in lines if l["src"] == "liveness"]
    assert [l["kind"] for l in lv] == ["binding", "heartbeat", "pid_dead"]
    assert lv[0]["payload"] == {"bound": True}
    assert lv[1]["payload"] == {} and lv[2]["payload"] == {}
    assert all(l["lineage_root"] == "S1" and l["profile"] == "A" for l in lv)
    assert "4242" not in json.dumps(lines)


def test_desktop_events_keep_status_and_error_code_only(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "meta.json").write_text(json.dumps({"name": "d", "host": "desktop", "profiles": ["A"], "t0": 1000.0,
                                               "recorded_at": "x", "model": "m", "runtime": "upstream",
                                               "runtime_sha": "f42f579cf8b", "notes": ""}))
    ev = [
        {"t": 1001000, "event": {"type": "session.info", "session_id": "rt1",
                                  "payload": {"stored_session_id": "S1", "cwd": "/home/adam/x", "title": "secret"}}},
        {"t": 1002000, "event": {"type": "message.complete", "session_id": "rt1",
                                  "payload": {"status": "error", "text": "my private reply",
                                              "error": "401 sk-abc", "error_surface": {"code": "provider_unreachable", "provider": "custom", "layer": "x"}}}},
        {"t": 1002500, "mark": "S1 start"},
    ]
    (raw / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    (raw / "states.jsonl").write_text(json.dumps({"t": 1000500, "reason": "x", "busyBySession": {"rt1": True}, "gateway": "open",
                                                  "focusedSessionId": "rt1", "focusedStoredSessionId": "S1", "profile": "default"}) + "\n")
    (raw / "dots.jsonl").write_text(
        json.dumps({"t": 1001500, "dots": "main:Needs your input|side:Needs your input"}) + "\n"
        + json.dumps({"t": 1003500, "dots": ""}) + "\n")
    db = sqlite3.connect(raw / "state-A.db")
    db.execute("create table sessions (id text primary key, parent_session_id text)")
    db.execute("insert into sessions values ('S1', null)")
    db.commit(); db.close()
    lines = convert.convert_desktop(raw)
    by = {(l["src"], l["kind"]): l for l in lines[1:]}
    assert by[("desktop.event", "session.info")]["payload"] == {"stored_session_id": "S1"}
    mc = by[("desktop.event", "message.complete")]
    assert mc["session"] == "rt1" and mc["payload"] == {"status": "error", "error_surface": {"code": "provider_unreachable"}}
    st = by[("desktop.state", "state")]
    assert st["payload"] == {"gateway": "open", "busy": True, "stored_session_id": "S1", "focused_session_id": "rt1", "focused_stored_session_id": "S1"} and st["session"] == "rt1"
    dots = [l for l in lines if l["src"] == "desktop.dot"]
    assert [d["payload"]["label"] for d in dots] == ["Needs your input", ""]
    assert all(d["session"] == "S1" and d["lineage_root"] == "S1" for d in dots)
    assert [l["t"] for l in lines[1:]] == sorted(l["t"] for l in lines[1:])
    blob = json.dumps(lines)
    for leak in ("private reply", "sk-abc", "/home/", "secret", "mark"):
        assert leak not in blob


def test_desktop_state_lines_carry_only_a_mapping_known_at_that_time(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "meta.json").write_text(json.dumps({"name": "d", "host": "desktop", "profiles": ["A"], "t0": 1000.0,
                                               "recorded_at": "x", "model": "m", "runtime": "upstream",
                                               "runtime_sha": "f42f579cf8b", "notes": ""}))
    (raw / "events.jsonl").write_text(json.dumps({"t": 1003000, "event": {"type": "session.info", "session_id": "rt2",
                                                  "payload": {"stored_session_id": "S2"}}}) + "\n")
    st = lambda t, busy, **kw: json.dumps({"t": t, "busyBySession": busy, "gateway": "open", "profile": "default", **kw}) + "\n"
    (raw / "states.jsonl").write_text(
        st(1001000, {"rt2": True})                                                       # before session.info, no focus: unmapped
        + st(1002000, {"rt2": True}, focusedSessionId="rt2", focusedStoredSessionId="S2")  # the host's own pair: mapped now
        + st(1004000, {"rt2": False, "rt3": True}))                                      # rt2 known from session.info by now
    (raw / "dots.jsonl").write_text("")
    db = sqlite3.connect(raw / "state-A.db")
    db.execute("create table sessions (id text primary key, parent_session_id text)")
    db.commit(); db.close()
    lines = [l for l in convert.convert_desktop(raw) if l["src"] == "desktop.state"]
    first, second, third_a, third_b = lines
    assert "stored_session_id" not in first["payload"] and "focused_session_id" not in first["payload"]      # no look-ahead
    assert second["payload"]["stored_session_id"] == "S2" and second["payload"]["focused_stored_session_id"] == "S2"
    assert (third_a["session"], third_a["payload"]["busy"], third_a["payload"]["stored_session_id"]) == ("rt2", False, "S2")
    assert third_b["session"] == "rt3" and "stored_session_id" not in third_b["payload"]
