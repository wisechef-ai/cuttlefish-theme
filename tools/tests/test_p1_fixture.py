"""Behaviour contract for the shared P1 fixture (tools/p1/stub-sessions.json).

The fixture is what makes the 3 direction renders comparable, so it must hold:
identity hues avoid the alarm arc (L7), every state is present, alarms carry literal text, and
any prefix of N sessions stays well spread (the 16- and 20-session identity gates).
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "tools" / "p1" / "stub-sessions.json"


def load():
    return json.loads(FX.read_text())


def circ(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def test_fixture_is_fresh():
    r = subprocess.run([sys.executable, str(ROOT / "tools/p1/make_stub_sessions.py"), "--check"], capture_output=True)
    assert r.returncode == 0, r.stdout.decode()


def test_twenty_sessions_unique_names_and_ids():
    s = load()["sessions"]
    assert len(s) == 20
    assert len({x["name"] for x in s}) == 20
    assert len({x["lineage_id"] for x in s}) == 20


def test_identity_hues_never_amber_or_red():
    for x in load()["sessions"]:
        assert 110 <= x["hue_deg"] < 340, x


def test_every_state_at_least_twice():
    fx = load()
    for st in fx["states"]:
        assert sum(x["state"] == st for x in fx["sessions"]) >= 2, st


def test_alarms_carry_literal_text_and_only_alarms():
    for x in load()["sessions"]:
        if x["state"] == "needs-you":
            assert x["alarm_text"].startswith("INPUT "), x
        elif x["state"] == "fault":
            assert x["alarm_text"].startswith("ERROR "), x
        else:
            assert x["alarm_text"] is None, x


def test_prefix_spread_at_16_and_20():
    s = load()["sessions"]
    # Hues never move once allocated, so 16 of 20 fixed slots must contain neighbours: the floor is
    # the 20-slot step. Small prefixes must do better (bit-reversal order): 8 sessions ≥ 2 steps.
    step = 230.0 / 20
    for n, floor in ((8, 2 * step), (16, step), (20, step)):
        hues = [x["hue_deg"] for x in s[:n]]
        gap = min(circ(a, b) for i, a in enumerate(hues) for b in hues[i + 1:])
        assert gap >= floor * 0.99, (n, gap)


def test_degraded_claims_no_identity():
    d = load()["degraded"]
    assert d["hue_deg"] is None and d["state"] == "unknown"
