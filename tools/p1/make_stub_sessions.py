#!/usr/bin/env python3
"""Generate tools/p1/stub-sessions.json, the ONE fixture every P1 direction renders.

Deterministic (no randomness), so re-running it is a no-op. Every direction and both gate
harnesses (G2, G5) read this file, so the renders compare like with like.

Identity hue (plan L7, P1-brief §4.2): OKLCh hue angle inside the identity arc
[110°, 340°). That arc excludes red (≈ 0–40°), orange (≈ 40–75°), amber/yellow (≈ 75–110°)
and red-magenta (340–360°), which are reserved for alarms. The 20 hues are spaced evenly
across the arc and handed out in bit-reversal order, so any prefix of N sessions is
near-maximally spread. This stands in for the P3 backend allocator. P1 only needs "same
hues for every direction". Directions choose their own L/C per state; the hue is the identity.

Usage: python3 tools/p1/make_stub_sessions.py [--check]
  --check  exit 1 if the committed JSON differs from what this script generates
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).with_name("stub-sessions.json")
ARC_START, ARC_END, N = 110.0, 340.0, 20

NAMES = [
    "ledger", "atlas", "quill", "harbor", "sprout", "vesper", "cobalt", "tidal",
    "fennel", "orbit", "juniper", "basalt", "wren", "lumen", "delta", "moss",
    "cinder", "kestrel", "marlin", "sable",
]
# Every one of the 6 states appears at least twice. Alarms carry literal ages (INPUT 4m / ERROR 2m).
STATES = [
    ("working", 0), ("needs-you", 240), ("idle", 0), ("fault", 120), ("working", 0),
    ("review", 0), ("idle", 0), ("unknown", 0), ("working", 0), ("idle", 0),
    ("needs-you", 45), ("idle", 0), ("fault", 900), ("working", 0), ("idle", 0),
    ("review", 0), ("idle", 0), ("unknown", 0), ("working", 0), ("idle", 0),
]


def bitrev_order(n: int) -> list[int]:
    bits = max(1, (n - 1).bit_length())
    order = sorted(range(1 << bits), key=lambda i: int(f"{i:0{bits}b}"[::-1], 2))
    return [i for i in order if i < n]


def age_label(state: str, age_s: int) -> str | None:
    if state == "needs-you":
        return f"INPUT {max(1, round(age_s / 60))}m" if age_s >= 60 else f"INPUT {age_s}s"
    if state == "fault":
        return f"ERROR {max(1, round(age_s / 60))}m" if age_s >= 60 else f"ERROR {age_s}s"
    return None


def build() -> dict:
    step = (ARC_END - ARC_START) / N
    slots = bitrev_order(N)
    sessions = []
    for i, name in enumerate(NAMES):
        state, age = STATES[i]
        hue = round(ARC_START + step * (slots[i] + 0.5), 2)
        sessions.append({
            "idx": i,
            "name": name,
            "lineage_id": f"20260930_{(i * 7919 + 104729) % 1000000:06d}_{name[:3]}",
            "hue_deg": hue,
            "state": state,
            "age_s": age,
            "alarm_text": age_label(state, age),
            "user_colored": i == 6,   # the desktop ledger case (a user pick wins; plugin must not overwrite)
            "focused": i == 0,
        })
    return {
        "schema": "cf2909.p1.stub-sessions/1",
        "identity_arc_deg": [ARC_START, ARC_END],
        "states": ["idle", "working", "review", "needs-you", "fault", "unknown"],
        "degraded": {
            "note": "no-binding mantle: HERMES_TUI_ACTIVE_SESSION_FILE unset/stale. Render as unknown, claim NO identity hue, label 'unbound'. Never the last known state.",
            "name": "unbound", "state": "unknown", "hue_deg": None, "alarm_text": None,
        },
        "sessions": sessions,
    }


def main() -> int:
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text() == text
        print("stub-sessions.json fresh" if ok else "stub-sessions.json STALE: re-run make_stub_sessions.py")
        return 0 if ok else 1
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(build()['sessions'])} sessions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
