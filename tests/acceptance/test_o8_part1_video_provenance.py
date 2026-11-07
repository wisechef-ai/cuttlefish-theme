"""ACCEPTANCE CONTRACT PART 1 — O8 demo-video provenance + the PR compare URL (closes luna F9) (locked).

Locked O8.5 checks the demo's duration and its first caption only. A 70-second video of one frame passes. Here the kit
must also hold `video/cut.json`, an edit decision list that says WHERE every second came from:

  {"schema": "cf2-cut/1", "output": "cuttlefish-v2-demo.mp4",
   "segments": [
     {"kind": "card", "name": "legend", "start": 0.0, "end": 9.5, "text": "Learn the language in 10 seconds",
      "legend": [{"state": "resting", "pattern": "mottle"}, {"state": "working", "pattern": "clouds"},
                 {"state": "needs_you", "pattern": "zebra"}, {"state": "error", "pattern": "blanch"},
                 {"state": "finished_unseen", "pattern": "eyespot"}]},
     {"kind": "capture", "start": 9.5, "end": 20.0, "source_sha256": "<capture.video_sha256 of evidence/v2/manifest.json>",
      "in": 12.0, "out": 22.5, "session": "<stored_id of a manifest session>", "state": "working"}, …]}

`start`/`end` are on the OUTPUT timeline (contiguous from 0); `in`/`out` are on the O7 capture. The segments' total equals the
ffprobe duration ±0.5 s; capture segments cover ≥ 4 distinct states and ≥ 4 distinct sessions, each (session, state) a pair
the O7 manifest recorded; the opener legend card occupies t ∈ [0, 10] s and shows all five patterns of SPEC C8.
`kit/PR-COMPARE-URL.txt` is ONE line: the URL Adam opens to start the PR from the local catalog branch:
  https://github.com/NousResearch/hermes-agent/compare/main...<user>:hermes-agent:catalog/cuttlefish-theme?expand=1
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import ROOT
from .test_o8_submission_kit import BRANCH, KIT

MANIFEST = ROOT / "evidence" / "v2" / "manifest.json"
DURATION_TOL_S = 0.5
OPENER_END_MAX_S = 10.0
MIN_STATES = 4
MIN_SESSIONS = 4
LEGEND = {"resting": "mottle", "working": "clouds", "needs_you": "zebra", "error": "blanch", "finished_unseen": "eyespot"}
URL_RE = re.compile(r"https://github\.com/NousResearch/hermes-agent/compare/main\.\.\.([A-Za-z0-9][A-Za-z0-9-]*):hermes-agent:"
                    r"([A-Za-z0-9._/-]+)\?expand=1")


def probe_duration(video: Path) -> float:
    if not shutil.which("ffprobe"):
        pytest.fail("ffprobe is needed to measure the demo")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _seg_problems(i: int, s: dict, prev_end: float) -> list[str]:
    where = f"segments[{i}]"
    bad = []
    if not all(isinstance(s.get(k), (int, float)) and not isinstance(s.get(k), bool) for k in ("start", "end")):
        return [f"{where}: start/end must be numbers"]
    if abs(s["start"] - prev_end) > 0.01:
        bad.append(f"{where}: starts at {s['start']}, the previous segment ended at {prev_end} (the cut must be contiguous from 0)")
    if s["end"] <= s["start"]:
        bad.append(f"{where}: end {s['end']} is not after start {s['start']}")
    if s.get("kind") not in ("card", "capture"):
        bad.append(f"{where}: kind must be 'card' or 'capture'")
    return bad


def _capture_problems(i: int, s: dict, manifest: dict) -> list[str]:
    where = f"segments[{i}]"
    cap = manifest["capture"]
    bad = []
    if s.get("source_sha256") != cap["video_sha256"]:
        bad.append(f"{where}: source_sha256 is not the O7 capture's ({cap['video_sha256'][:12]}…)")
    lo, hi = s.get("in"), s.get("out")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lo, hi)) or lo < 0 or hi <= lo:
        return bad + [f"{where}: in/out must be numbers with 0 <= in < out"]
    if abs((hi - lo) - (s["end"] - s["start"])) > 0.05:
        bad.append(f"{where}: out−in ({hi - lo:.2f}) differs from end−start ({s['end'] - s['start']:.2f})")
    pairs = {(x["stored_id"], x["expected"]) for x in cap["sessions"]}
    if (s.get("session"), s.get("state")) not in pairs:
        bad.append(f"{where}: ({s.get('session')}, {s.get('state')}) is not a session/state pair the O7 manifest recorded")
    return bad


def _opener_problems(segs: list[dict]) -> list[str]:
    first = segs[0] if segs else {}
    if first.get("kind") != "card" or first.get("name") != "legend":
        return ["the first segment must be the legend card (kind 'card', name 'legend')"]
    bad = []
    if first.get("start") != 0 or not (isinstance(first.get("end"), (int, float)) and first["end"] <= OPENER_END_MAX_S):
        bad.append(f"the legend card must occupy t ∈ [0, {OPENER_END_MAX_S:.0f}] s, it covers [{first.get('start')}, {first.get('end')}]")
    shown = {x.get("state"): x.get("pattern") for x in first.get("legend", []) if isinstance(x, dict)}
    if shown != LEGEND:
        bad.append(f"the legend card must show exactly {LEGEND}, it shows {shown}")
    return bad


def _timeline_problems(segs: list[dict], manifest: dict) -> list[str]:
    bad, prev = [], 0.0
    for i, s in enumerate(segs):
        found = _seg_problems(i, s, prev)
        if found and "numbers" in found[0]:
            return bad + found
        bad += found
        prev = s["end"]
        if s.get("kind") == "capture":
            bad += _capture_problems(i, s, manifest)
    return bad


def _spread_problems(segs: list[dict]) -> list[str]:
    caps = [s for s in segs if s.get("kind") == "capture"]
    bad = []
    for what, floor in (("state", MIN_STATES), ("session", MIN_SESSIONS)):
        n = len({s.get(what) for s in caps})
        if n < floor:
            bad.append(f"capture segments show {n} distinct {what}s (< {floor})")
    return bad


def cut_problems(cut: dict, manifest: dict, video_s: float) -> list[str]:
    """Every reason `cut` is not an honest edit decision list of a video that lasts `video_s` seconds."""
    if cut.get("schema") != "cf2-cut/1" or not isinstance(cut.get("segments"), list) or not cut["segments"]:
        return ["cut.json: schema must be 'cf2-cut/1' with a non-empty segments list"]
    segs = [s for s in cut["segments"] if isinstance(s, dict)]
    if len(segs) != len(cut["segments"]):
        return ["cut.json: every segment must be an object"]
    bad = _opener_problems(segs) + _timeline_problems(segs, manifest)
    if any("numbers" in p for p in bad):
        return bad
    total = sum(s["end"] - s["start"] for s in segs)
    if abs(total - video_s) > DURATION_TOL_S:
        bad.append(f"segments sum to {total:.2f} s, the video lasts {video_s:.2f} s (±{DURATION_TOL_S})")
    return bad + _spread_problems(segs)


def url_problems(text: str) -> list[str]:
    lines = text.split("\n")
    if lines[-1] != "" or len(lines) != 2:
        return ["PR-COMPARE-URL.txt must be exactly one line ending in a newline"]
    m = URL_RE.fullmatch(lines[0])
    if not m:
        return [f"not the compare URL form main...<user>:hermes-agent:<branch>?expand=1: {lines[0]!r}"]
    return [] if m.group(2) == BRANCH else [f"the compare branch must be {BRANCH}, it is {m.group(2)}"]


# ---- the kit --------------------------------------------------------------------------------------------------------

def test_V1_the_demo_has_a_cut_list_that_adds_up_to_the_video_and_comes_from_the_capture():
    cut_file = KIT / "video" / "cut.json"
    assert cut_file.is_file(), f"{cut_file} missing: the edit decision list of the demo"
    assert MANIFEST.is_file(), f"{MANIFEST.relative_to(ROOT)} missing: the cut is bound to the O7 capture"
    cut = json.loads(cut_file.read_text())
    video = KIT / "video" / cut.get("output", "cuttlefish-v2-demo.mp4")
    assert video.is_file(), f"{video} missing"
    problems = cut_problems(cut, json.loads(MANIFEST.read_text()), probe_duration(video))
    assert problems == [], "\n".join(problems)


def test_V2_the_pr_compare_url_is_ready_for_adam_to_open():
    f = KIT / "PR-COMPARE-URL.txt"
    assert f.is_file(), f"{f} missing: the compare URL Adam opens"
    assert url_problems(f.read_text()) == []


# ---- the validators themselves (no kit, no evidence needed) -------------------------------------------------------------

def good() -> tuple[dict, dict]:
    sha = "a" * 64
    states = ["working", "needs_you", "error", "resting"]
    manifest = {"capture": {"video_sha256": sha, "sessions": [{"stored_id": f"S{i}", "expected": st} for i, st in enumerate(states)]}}
    legend = [{"state": k, "pattern": v} for k, v in LEGEND.items()]
    segs = [{"kind": "card", "name": "legend", "start": 0.0, "end": 9.5, "legend": legend}]
    t = 9.5
    for i, st in enumerate(states):
        segs.append({"kind": "capture", "start": t, "end": t + 15, "source_sha256": sha, "in": 10.0 * i, "out": 10.0 * i + 15,
                     "session": f"S{i}", "state": st})
        t += 15
    return {"schema": "cf2-cut/1", "segments": segs}, manifest


def test_V3_a_good_cut_passes():
    cut, manifest = good()
    assert cut_problems(cut, manifest, 69.5) == []
    assert cut_problems(cut, manifest, 69.9) == [], "within ±0.5 s of ffprobe"


def test_V4_the_validator_rejects_each_dishonest_cut():
    def mutate(f):
        cut, manifest = good()
        f(cut, manifest)
        return cut_problems(cut, manifest, 69.5)
    assert any("sum" in p for p in mutate(lambda c, m: c["segments"][-1].update(end=c["segments"][-1]["end"] + 5)))
    assert any("sum" in p for p in cut_problems(*good(), 70.5))
    assert any("source_sha256" in p for p in mutate(lambda c, m: c["segments"][1].update(source_sha256="b" * 64)))
    assert any("not a session/state pair" in p for p in mutate(lambda c, m: c["segments"][1].update(state="error")))
    assert any("distinct states" in p for p in mutate(lambda c, m: [s.update(state="working", session="S0") for s in c["segments"][1:]]))
    assert any("distinct sessions" in p for p in mutate(lambda c, m: [m["capture"]["sessions"][i].update(stored_id="S0")
                                                                       or c["segments"][i + 1].update(session="S0") for i in range(4)]))
    assert any("contiguous" in p for p in mutate(lambda c, m: c["segments"][2].update(start=c["segments"][2]["start"] + 2)))
    assert any("legend card must occupy" in p for p in mutate(lambda c, m: c["segments"][0].update(end=12.0)))
    assert any("legend card must show" in p for p in mutate(lambda c, m: c["segments"][0].update(legend=c["segments"][0]["legend"][:4])))
    assert any("first segment" in p for p in mutate(lambda c, m: c["segments"][0].update(name="intro")))
    assert any("out−in" in p for p in mutate(lambda c, m: c["segments"][1].update(out=40.0)))
    assert any("in/out" in p for p in mutate(lambda c, m: c["segments"][1].update(out=-1)))
    assert any("schema" in p for p in cut_problems({"schema": "x"}, good()[1], 1))
    assert any("start/end" in p for p in mutate(lambda c, m: c["segments"][1].update(start="0")))


def test_V5_the_url_validator():
    ok = "https://github.com/NousResearch/hermes-agent/compare/main...someone:hermes-agent:catalog/cuttlefish-theme?expand=1\n"
    assert url_problems(ok) == []
    assert url_problems(ok.rstrip("\n"))
    assert url_problems(ok + ok)
    assert url_problems(ok.replace("expand=1", "expand=0"))
    assert url_problems(ok.replace("NousResearch", "evil"))
    assert url_problems(ok.replace("catalog/cuttlefish-theme", "main"))
    assert url_problems(ok.replace("main...", "main.."))
    assert url_problems(" " + ok)
