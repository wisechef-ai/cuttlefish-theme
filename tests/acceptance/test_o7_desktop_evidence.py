"""ACCEPTANCE CONTRACT — O4 (measured half) + O7: evidence from a REAL Desktop build, isolated (locked).

The harness (tools/desktop/) writes evidence/v2/manifest.json. This test only VERIFIES it: fresh (made from the
plugin.js in this tree), isolated (never Adam's home, gateway or display), 4 live sessions in 4 distinct states as the
DOM reports them, pixel measurements of the real field, idle CPU against the budget set BEFORE measuring
(PLAN.md §4), and a vision critique by a model from a different family than the builders.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import ROOT, is_live

MANIFEST = ROOT / "evidence" / "v2" / "manifest.json"
BUDGET_IDLE_PP = 1.0      # plugin on − off, renderer+GPU CPU, % of one core, focused session resting, 8 sessions, 60 s
BUDGET_WORKING_PP = 6.0   # same, focused session working (clouds moving)
FLOOR_FIELD_UPDATES_PER_S = 4.0
BUILDER_FAMILIES = ("claude", "sonnet", "haiku", "opus", "anthropic")


@pytest.fixture(scope="module")
def m() -> dict:
    assert MANIFEST.is_file(), f"{MANIFEST.relative_to(ROOT)} missing: run the real-Desktop harness (make evidence)"
    return json.loads(MANIFEST.read_text())


def _path(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_O7_1_fresh_and_pinned(m):
    assert m["plugin_js_sha256"] == _sha(ROOT / "desktop" / "plugin.js"), "evidence was made from a different plugin.js"
    assert m["core"]["version"] == "v0.22.7" and m["core"]["sha"].startswith("b200f5bc60e")
    assert m["core"]["desktop_build"] == "source", "a real Desktop build from the pinned core source"


def test_O7_2_isolated(m):
    iso = m["isolation"]
    home = Path(iso["hermes_home"]).resolve()
    assert not is_live(home), f"captured against {home}"
    assert "cache" not in home.parts or "sandboxes" in home.parts, "a durable sandbox, not a scratch dir the pruner eats"
    assert not str(Path(iso["user_data_dir"]).resolve()).startswith(str((Path.home() / ".config").resolve())), "own userData"
    assert iso["gateway_port"] not in iso["live_gateway_ports"], "the capture's gateway is not Adam's"
    assert iso["display"] not in (":0", ":1"), "never Adam's display"
    assert iso["isolated_backend"] is True


def test_O7_3_four_live_sessions_in_four_states(m):
    sessions = m["capture"]["sessions"]
    assert len(sessions) >= 4
    assert len({s["expected"] for s in sessions}) >= 4, "four DIFFERENT states"
    for s in sessions:
        assert s["dom_state"] == s["expected"], f"{s['stored_id']}: DOM says {s['dom_state']}, scenario {s['expected']}"
        assert s["dom_state"] in {"resting", "working", "needs_you", "error", "finished_unseen"}
    assert m["capture"]["rows_with_swatch"] == m["capture"]["rows_total"] and m["capture"]["rows_total"] >= 4, \
        "every sidebar row carries a swatch"


def test_O7_4_capture_files_exist_and_match(m):
    cap = m["capture"]
    video = _path(cap["video"])
    assert video.is_file() and _sha(video) == cap["video_sha256"]
    if shutil.which("ffprobe"):
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                 capture_output=True, text=True, check=True).stdout.strip())
        assert d >= 20, f"capture is {d:.1f} s"
    assert len(cap["stills"]) >= 5, "a still per state at least"
    for s in cap["stills"]:
        p = _path(s["path"])
        assert p.is_file() and _sha(p) == s["sha256"], s["path"]


def test_O7_5_real_pixels_match_the_language(m):
    px = m["field_pixels"]
    assert px["resting"]["p95_dL"] <= 0.05, "near-invisible at rest, measured on the real screen"
    assert px["resting"]["organs_detected"] >= 20, "…but present"
    assert px["needs_you"]["highK"] >= 0.6, "needs-you stripes are there in real pixels"
    assert px["needs_you"]["mean_dL"] >= 2 * px["resting"]["mean_dL"]


def test_O7_6_idle_cpu_within_the_preset_budget(m):
    p = m["perf"]
    assert p["sessions"] >= 8 and p["window_s"] >= 60
    assert p["budget"] == {"idle_pp": BUDGET_IDLE_PP, "working_pp": BUDGET_WORKING_PP}, "the budget was not moved"
    idle = p["idle"]["on_pct"] - p["idle"]["off_pct"]
    work = p["working"]["on_pct"] - p["working"]["off_pct"]
    assert idle <= BUDGET_IDLE_PP, f"idle delta {idle:.2f} pp > {BUDGET_IDLE_PP}"
    assert work <= BUDGET_WORKING_PP, f"working delta {work:.2f} pp > {BUDGET_WORKING_PP}"
    assert p["working"]["field_updates_per_s"] >= FLOOR_FIELD_UPDATES_PER_S, "the clouds really moved during the measurement"


def test_O7_7_vision_critique_by_another_family(m):
    v = m["vision"]
    assert not any(f in v["model"].lower() for f in BUILDER_FAMILIES), f"{v['model']} is a builder family"
    assert v["builder_models"], "name the builders so the check is auditable"
    assert _path(v["file"]).is_file()
    assert v["verdicts"] == {"readable_at_a_glance": True, "five_states_distinguishable": True, "not_distracting_at_rest": True}


@pytest.mark.skipif(os.environ.get("CF_STRICT") != "1", reason="evidence is produced by the lead's harness run")
def test_O7_0_manifest_exists():
    assert MANIFEST.is_file()
