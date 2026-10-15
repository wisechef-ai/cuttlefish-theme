"""tools/make_contract_vectors.py: the shared goldens for the TS core."""
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "make_contract_vectors.py"
SPEC = REPO / "packages" / "core" / "spec"
HOOKS = {"on_session_reset", "on_session_start", "pre_llm_call", "pre_verify", "post_llm_call", "on_session_end",
         "pre_tool_call", "post_tool_call", "pre_approval_request", "post_approval_response",
         "api_request_error", "on_session_finalize"}


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=120)


def test_committed_vectors_are_in_sync_with_the_reference():
    r = run("--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run("--out-dir", str(a)).returncode == 0 and run("--out-dir", str(b)).returncode == 0
    for n in ("identity-vectors.json", "state-vectors.json"):
        assert (a / n).read_bytes() == (b / n).read_bytes() == (SPEC / n).read_bytes()


def test_check_exits_1_on_drift(tmp_path):
    assert run("--out-dir", str(tmp_path)).returncode == 0
    f = tmp_path / "identity-vectors.json"
    d = json.loads(f.read_text())
    d["cases"][0]["expected_hue_cd"] += 1
    f.write_text(json.dumps(d))
    assert run("--check", "--out-dir", str(tmp_path)).returncode == 1
    assert run("--check", "--out-dir", str(tmp_path / "nowhere")).returncode == 1


def test_identity_vectors_cover_the_required_shapes():
    cases = json.loads((SPEC / "identity-vectors.json").read_text())["cases"]
    assert len(cases) >= 300
    for c in cases:
        assert set(c) >= {"lineage_root", "peers_cd", "expected_hue_cd", "expected_base", "digest_hex"}
        assert isinstance(c["expected_hue_cd"], int) and len(c["digest_hex"]) == 16
    n = [len(c["peers_cd"]) for c in cases]
    assert 0 in n and any(1 <= x <= 3 for x in n) and any(8 <= x <= 24 for x in n)
    assert any(len(set(c["peers_cd"])) < len(c["peers_cd"]) for c in cases)  # duplicate peers
    assert any(not c["lineage_root"].isascii() for c in cases)


def test_state_vectors_cover_every_hook_and_every_output_state():
    cases = json.loads((SPEC / "state-vectors.json").read_text())["cases"]
    assert len(cases) >= 40
    hooks, outs = set(), set()
    for c in cases:
        assert len(c["events"]) == len(c["expected_states_after_each_event"]) and c["events"]
        hooks |= {e["hook"] for e in c["events"]}
        outs |= {s["state"] for s in c["expected_states_after_each_event"]}
        for e in c["events"]:
            assert set(e) == {"hook", "ts", "session_id", "tool_name", "tool_call_id", "turn_id", "completed"}
    assert HOOKS <= hooks
    assert outs == {"idle", "working", "review", "needs-you", "fault", "unknown"}
    names = " ".join(c["name"] for c in cases)
    for w in ("reask", "401", "rotation", "finalize", "reset"):
        assert w in names
