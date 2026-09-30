"""Spike 13 measurement contract (settle.py). Pure — no pty, no node.

The regression at the heart of this file: the original detector accepted a 3-s chunk under 200 bytes as "quiet".
Real startup (measured 2026-09-30 on hermes-agent f42f579, 1-s windows) goes: `summoning hermes…` and
`forging session…` sit completely silent for ~6-8 s, THEN `starting agent…` writes ~4 kB/s for ~5 s, THEN `ready`
at ~45 B/s. The old detector declared "quiet" during the silent pre-agent lull, so the idle control measured the
spinner that followed (the reviewer's off control: `starting agent…`, 840.6 B/s).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SETTLE = Path(__file__).resolve().parents[1] / "spikes" / "13-mantle-repaint-latency" / "settle.py"
spec = importlib.util.spec_from_file_location("spike13_settle", SETTLE)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def w(b, status, secs=1.0):
    return {"bytes": b, "secs": secs, "status": status}


# Measured 1-s trace of a fresh-home boot (probe run, off mode), abbreviated to the shape that matters.
STARTUP = ([w(141, None), w(2827, None)] + [w(0, None)] * 8 + [w(2540, None)] + [w(0, None)] * 5
           + [w(8366, "starting agent"), w(4360, "starting agent"), w(4205, "starting agent"),
              w(3501, "starting agent"), w(4098, "starting agent"), w(1284, "ready")]
           + [w(45, "ready"), w(45, "ready"), w(45, "ready"), w(98, "ready"), w(45, "ready")])


def test_legacy_detector_accepts_the_contaminated_startup_and_new_contract_rejects_it():
    # Reviewer-requested shape: a short spinner chunk, THEN later non-quiet output.
    seq = [w(0, None), w(12, None), w(0, None),                      # 3 s silent pre-agent lull (<200 B total)
           w(4360, "starting agent"), w(4205, "starting agent"), w(3501, "starting agent")]
    first_chunk = sum(x["bytes"] for x in seq[:3])
    assert S.legacy_quiet(first_chunk), "old detector must have called the lull quiet (that is the bug)"
    # ...and what followed was not quiet at all:
    assert sum(x["bytes"] for x in seq[3:]) / 3 > 800
    assert S.settled_index(seq) is None, "new contract must not settle on a lull that precedes a spinner"


def test_new_contract_settles_only_after_ready_and_consecutive_quiet():
    i = S.settled_index(STARTUP)
    assert i is not None and STARTUP[i]["status"] == "ready"
    first_ready = next(k for k, x in enumerate(STARTUP) if x["status"] == "ready")
    assert STARTUP[first_ready]["bytes"] > S.MAX_IDLE_BPS            # the ready-transition repaint itself is loud
    assert i == first_ready + S.SETTLE_NEED, i                       # so the streak is the NEXT 3 windows
    assert all(x["status"] == "ready" and x["bytes"] <= S.MAX_IDLE_BPS for x in STARTUP[i - 2:i + 1])
    # every legacy 3-s chunk before `starting agent` was "quiet" to the old detector
    lull = STARTUP[3:6]
    assert S.legacy_quiet(sum(x["bytes"] for x in lull)) and lull[0]["status"] is None


def test_one_quiet_ready_window_is_not_enough():
    seq = [w(45, "ready"), w(3249, "ready"), w(45, "ready"), w(45, "ready")]
    assert S.settled_index(seq) is None
    assert S.settled_index(seq + [w(46, "ready")]) == 4


def test_a_nonready_window_breaks_the_streak():
    seq = [w(45, "ready"), w(45, "ready"), w(0, "starting agent"), w(45, "ready"), w(45, "ready")]
    assert S.settled_index(seq) is None


def test_anim_streak_requires_steady_frames_not_quiet():
    frames = [w(9500, "ready"), w(9600, "ready"), w(9400, "ready")]
    assert S.settled_index(frames) is None                       # not quiet — correct for off/static
    assert S.settled_index(frames, anim=True) == 2
    burst = [w(30000, "ready"), w(9500, "ready"), w(9500, "ready")]   # resize/startup burst in the streak
    assert S.settled_index(burst, anim=True) is None
    assert S.settled_index([w(9500, "starting agent")] + frames[:2], anim=True) is None


def test_status_parser_reads_the_real_status_bar():
    assert S.status_of(["", "─ ready │ stub │ 19s │ voice off │ 1 session      ─ ~ (master)"]) == "ready"
    assert S.status_of(["─ starting agent… │ stub │ 0s │ voice off     ─ ~ (master)"]) == "starting agent"
    assert S.status_of(["─ summoning hermes… │  │ voice off"]) is None
    assert S.status_of(["plain text ready"]) is None


@pytest.mark.parametrize("idle,mode,bad", [
    # reviewer repro13: off control still starting, 840.6 B/s
    ({"settled": True, "status_start": "starting agent", "status_end": "starting agent", "bytes_per_s": 840.6}, "off", True),
    # reviewer repro13b: static control 3,249 B/s at "ready"
    ({"settled": True, "status_start": "ready", "status_end": "ready", "bytes_per_s": 3249.0}, "static", True),
    ({"settled": False, "status_start": "ready", "status_end": "ready", "bytes_per_s": 45.0}, "off", True),
    ({"settled": True, "status_start": "ready", "status_end": "ready", "bytes_per_s": 50.3}, "static", False),
    ({"settled": True, "status_start": "ready", "status_end": "ready", "bytes_per_s": 9515.0}, "anim", False),
])
def test_contaminated_controls_from_the_review_are_invalid(idle, mode, bad):
    assert bool(S.validate_idle(idle, mode)) is bad


def test_classification_is_three_way_against_the_unchanged_budget():
    assert S.G3_BUDGET_MS == 2.0
    assert S.classify_run((-1.0, 1.9)) == "pass"
    assert S.classify_run((2.1, 9.0)) == "fail"
    assert S.classify_run((-3.0, 6.0)) == "indeterminate"
    assert S.classify_gate(["pass", "pass"]) == "indeterminate"          # < 3 valid runs
    assert S.classify_gate(["pass"] * 3) == "pass"
    assert S.classify_gate(["fail"] * 3) == "fail"
    assert S.classify_gate(["pass", "fail", "pass"]) == "indeterminate"


def test_bootstrap_ci_brackets_a_known_shift_and_is_seeded():
    import random
    rng = random.Random(1)
    off = [10 + rng.expovariate(0.5) for _ in range(240)]
    anim = [x + 8 for x in off]
    lo, hi = S.bootstrap_delta_ci(off, anim)
    assert lo <= 8 <= hi and lo > 2
    assert S.bootstrap_delta_ci(off, anim) == (lo, hi)
    assert S.classify_run((lo, hi)) == "fail"


def _load_summarize():
    import sys
    sys.path.insert(0, str(SETTLE.parent))
    sp = importlib.util.spec_from_file_location("spike13_summarize", SETTLE.parent / "summarize.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _res(tmp_path, name, valid, cls="pass", fps="4"):
    import json
    meta = {"fps": fps, "quant": "48", "memo": "1", "rle": "1"}
    r = {"meta": meta, "valid": valid, "problems": [] if valid else ["idle off: status_start='starting agent'"]}
    if valid:
        r["verdict_inputs"] = {"p95_off": 10.0, "p95_static": 11.0, "p95_anim": 11.5, "anim_minus_off_p95_ms": 1.5,
                               "anim_minus_off_p95_ci95": [-1.0, 1.9 if cls == "pass" else 5.0],
                               "static_minus_off_p95_ms": 1.0, "static_minus_off_p95_ci95": [-1.0, 1.5],
                               "per_round_anim_minus_off_p95": [1, 2, 1, 2], "g3_run_class": cls, "g3_static_run_class": "pass",
                               "static_idle_bytes": 451, "static_idle_cpu_pct": 0.9, "off_idle_bytes": 451, "off_idle_cpu_pct": 0.6,
                               "anim_bytes_per_s": 9600.0, "anim_cpu_pct": 9.0}
    d = tmp_path / name
    d.mkdir()
    (d / "results.json").write_text(json.dumps(r))
    return str(d / "results.json")


def test_summarize_never_scores_invalid_runs_and_needs_three_valid(tmp_path):
    M = _load_summarize()
    two_pass_one_invalid = [_res(tmp_path, "a", True), _res(tmp_path, "b", True), _res(tmp_path, "c", False)]
    out = M.summarize(two_pass_one_invalid)["fps4-q48-memo1-rle1"]
    assert (out["valid_runs"], out["invalid_runs"], out["g3_anim"]) == (2, 1, "indeterminate")
    out = M.summarize(two_pass_one_invalid + [_res(tmp_path, "d", True)])["fps4-q48-memo1-rle1"]
    assert out["g3_anim"] == "pass"
    out = M.summarize(two_pass_one_invalid + [_res(tmp_path, "e", True, cls="indeterminate")])["fps4-q48-memo1-rle1"]
    assert out["g3_anim"] == "indeterminate"


def test_summarize_treats_legacy_results_without_contract_as_invalid(tmp_path):
    import json
    M = _load_summarize()
    d = tmp_path / "legacy"
    d.mkdir()
    (d / "results.json").write_text(json.dumps({"meta": {"fps": "4"}, "verdict_inputs": {"anim_minus_off_p95_ms": 1.1}}))
    out = M.summarize([str(d / "results.json")])["fps4-q0-memo0-rle0"]
    assert out["valid_runs"] == 0 and out["g3_anim"] == "indeterminate"


def test_pooled_ci_is_stratified_and_brackets_a_known_shift():
    import random
    rng = random.Random(2)
    pairs = []
    for base in (8, 12, 20):          # runs at different host baselines
        off = [base + rng.expovariate(0.5) for _ in range(240)]
        pairs.append((off, [x + 5 for x in off]))
    lo, hi = S.pooled_delta_ci(pairs, n=400)
    assert lo < 5 < hi + 1e-9 and lo > 2
