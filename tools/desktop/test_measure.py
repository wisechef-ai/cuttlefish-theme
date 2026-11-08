"""Pytest for measure.py (dev only): the small-window exclusion rule, the union of exclusions, the ink centroid, the still guard.

    .venv/bin/python -m pytest tools/desktop/test_measure.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure as M  # noqa: E402

IP = M.load("instruments_py")
RE = M.load("raw_evidence")


def _png(path: Path, w: int, h: int, black=None) -> Path:
    """A white still with an optional black block (x0, y0, x1, y1), written with the contract's own PNG writer."""
    rows = []
    for y in range(h):
        row = bytearray(b"\xff" * (3 * w))
        if black and black[1] <= y < black[3]:
            for x in range(black[0], black[2]):
                row[3 * x:3 * x + 3] = b"\x00\x00\x00"
        rows.append(bytes(row))
    IP.write_png(path, w, h, rows)
    return path


# ---- the exclusion verdict: the same branches as evidence_lib.ts exclusionVerdict -------------------------------------------
def test_within_the_share_is_ok_and_reports_both_numbers():
    v = M.exclusion_verdict(1_000_000, 200_000)
    assert v["ok"] is True and v["reason"] is None
    assert v["share"] == 0.2 and v["measured"] == 800_000


def test_a_small_window_over_25_percent_passes_while_enough_field_remains():
    v = M.exclusion_verdict(400_000, 112_000)  # 28 %, 288 000 px left: the 1280x800 case
    assert v["ok"] is True and v["share"] > 0.25 and v["measured"] == 288_000
    assert "28% excluded" in v["reason"] and "288000 px" in v["reason"]


def test_too_little_field_left_fails_whatever_the_share():
    v = M.exclusion_verdict(300_000, 150_000)
    assert v["ok"] is False and "too little field left to measure" in v["reason"]


def test_the_boundaries_are_exact():
    assert M.exclusion_verdict(1_000_000, 250_000)["reason"] is None  # 25 % exactly
    assert M.exclusion_verdict(400_000, 200_000)["ok"] is True  # MIN_MEASURED_PX left exactly
    assert M.exclusion_verdict(400_000, 200_001)["ok"] is False
    assert M.MIN_MEASURED_PX == 200_000 and M.MAX_EXCLUDED_SHARE == 0.25  # the same constants as evidence_lib.ts
    with pytest.raises(ValueError):
        M.exclusion_verdict(0, 0)


# ---- geometry ---------------------------------------------------------------------------------------------------------------
def test_union_area_counts_overlaps_once_and_clips_to_the_region():
    assert M.union_area([(0, 0, 10, 10), (5, 5, 10, 10)], (0, 0, 20, 20)) == 175
    assert M.union_area([(-5, -5, 10, 10)], (0, 0, 20, 20)) == 25
    assert M.union_area([], (0, 0, 20, 20)) == 0


# ---- the ink centroid (the working-frame pick) -------------------------------------------------------------------------------
def test_centroid_of_a_black_block_on_white(tmp_path):
    png = _png(tmp_path / "s.png", 100, 60, black=(70, 10, 80, 20))
    c = M.centroid_of(png, [0, 0, 100, 60], [])
    assert c == {"cx": 74.5, "cy": 14.5, "n": 100}


def test_centroid_ignores_excluded_ink(tmp_path):
    png = _png(tmp_path / "s.png", 100, 60, black=(70, 10, 80, 20))
    c = M.centroid_of(png, [0, 0, 100, 60], [[70, 0, 5, 60]])  # the left half of the block is excluded
    assert c == {"cx": 77.0, "cy": 14.5, "n": 50}


def test_no_ink_means_no_centroid(tmp_path):
    assert M.centroid_of(_png(tmp_path / "w.png", 40, 30), [0, 0, 40, 30], []) is None


# ---- the still guard: contract bounds + the 50 % region rule, then the honest exclusion rule ---------------------------
def test_check_still_accepts_a_small_window_still_over_the_share():
    meta = {"region": [0, 0, 1000, 800], "exclude": [[0, 0, 1000, 240]]}  # 30 % of 800 000 px excluded: 560 000 left
    v = M.check_still(RE, meta, 1280, 800)  # a 1280x800 still: the region is 78 % of it, so the contract's bounds hold
    assert v["ok"] is True and round(v["share"], 2) == 0.3 and v["measured"] == 560_000


def test_check_still_refuses_too_little_field():
    meta = {"region": [0, 0, 1000, 800], "exclude": [[0, 0, 1000, 720]]}  # 90 %: 80 000 px left
    with pytest.raises(ValueError, match="too little field left"):
        M.check_still(RE, meta, 1280, 800)


def test_check_still_keeps_the_contract_region_rule():
    meta = {"region": [0, 0, 300, 200], "exclude": []}  # 60 000 px of a 1600x1000 still: under half, the contract refuses
    with pytest.raises(ValueError, match="< 50%"):
        M.check_still(RE, meta, 1600, 1000)
