"""Measure what the theme ACTUALLY paints against the reference renders' structure.

Reference targets come from tools/../docs/reference-structure.md (8 mock-ups read
by vision): near-black ground (OKLab L 0.05-0.10), lit fraction 5-25%, dots
0.06-0.2 glyph-heights, 7-15 distinct tones, multi-scale envelopes 5-35 glyphs.

Run:  python3 tools/measure_vs_reference.py
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "cuttlefish_theme", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)])
pkg = importlib.util.module_from_spec(spec)
sys.modules["cuttlefish_theme"] = pkg
spec.loader.exec_module(pkg)

from cuttlefish_theme.linework import cells  # noqa: E402
from cuttlefish_theme.color.oklab import hex_to_oklch  # noqa: E402

SESSIONS = [f"s{n}" for n in range(40)]
WIDTH = 100


def bg(style: str) -> str:
    return style.split("bg:", 1)[1].split()[0]


def rule_stats(sid: str) -> dict:
    row = cells(sid, "resting", WIDTH)
    grounds = Counter(b for _f, b, _g in row)
    ground_hex, ground_n = grounds.most_common(1)[0]
    fgs = {f for f, b, _g in row if f != b}
    return {
        "ground_hex": ground_hex,
        "ground_L": hex_to_oklch(ground_hex).L,
        "lit_frac": sum(1 for f, b, _g in row if f != b) / WIDTH,
        "distinct_lit": len(fgs),
        "lit_L_range": (min((hex_to_oklch(f).L for f in fgs), default=0),
                        max((hex_to_oklch(f).L for f in fgs), default=0)),
    }


def mean(key, rows):
    return sum(r[key] for r in rows) / len(rows)


r = [rule_stats(s) for s in SESSIONS]

# The transcript mantle is GONE (2026-09-13): the transcript is flat near-black
# and the art lives on the chrome, so there is no per-line field left to score.
print("=== INPUT RULE (one row) ===")
print(f"  ground hex / L           {r[0]['ground_hex']}  {mean('ground_L', r):6.3f}   Adam: flat single colour")
print(f"  lit fraction             {mean('lit_frac', r):6.3f}   Adam: 'dots scattered on it'")
print(f"  distinct lit tones       {mean('distinct_lit', r):6.1f}")
print(f"  distinct grounds across sessions {len({x['ground_hex'] for x in r})} / {len(SESSIONS)}")
