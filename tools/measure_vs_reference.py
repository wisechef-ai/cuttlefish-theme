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

from cuttlefish_theme.chrome import _mantle_row  # noqa: E402
from cuttlefish_theme.linework import cells  # noqa: E402
from cuttlefish_theme.color.oklab import hex_to_oklch  # noqa: E402

SESSIONS = [f"s{n}" for n in range(40)]
WIDTH, ROWS = 100, 30


def bg(style: str) -> str:
    return style.split("bg:", 1)[1].split()[0]


def mantle_stats(sid: str) -> dict:
    rows = [[bg(s) for s, _ in _mantle_row(sid, WIDTH, r)] for r in range(ROWS)]
    flat = [c for row in rows for c in row]
    tones = Counter(flat)
    ground_hex, ground_n = tones.most_common(1)[0]
    Ls = [hex_to_oklch(c).L for c in tones]
    # vertical correlation: fraction of cells identical to the row above
    same = sum(a == b for r in range(1, ROWS) for a, b in zip(rows[r], rows[r - 1]))
    # horizontal run lengths
    runs, cur = [], 1
    for r in rows:
        for i in range(1, WIDTH):
            if r[i] == r[i - 1]:
                cur += 1
            else:
                runs.append(cur); cur = 1
        runs.append(cur); cur = 1
    return {
        "tones": len(tones),
        "ground_L": hex_to_oklch(ground_hex).L,
        "ground_hex": ground_hex,
        "lit_frac": 1 - ground_n / len(flat),
        "L_min": min(Ls), "L_max": max(Ls),
        "L_spread": max(Ls) - min(Ls),
        "vcorr": same / ((ROWS - 1) * WIDTH),
        "mean_run": sum(runs) / len(runs),
        "single_runs": sum(r == 1 for r in runs) / len(runs),
    }


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


m = [mantle_stats(s) for s in SESSIONS]
r = [rule_stats(s) for s in SESSIONS]

print(f"=== TRANSCRIPT MANTLE ({len(SESSIONS)} sessions, {WIDTH}x{ROWS}) ===")
print(f"  distinct tones/session   {mean('tones', m):6.1f}   reference 7-15")
print(f"  ground OKLab L           {mean('ground_L', m):6.3f}   reference 0.05-0.10  <-- ground darkness")
print(f"  lit fraction             {mean('lit_frac', m):6.3f}   reference 0.05-0.25")
print(f"  lightness spread in field{mean('L_spread', m):6.3f}   (text legibility: lower is safer)")
print(f"  vertical correlation     {mean('vcorr', m):6.3f}   contract >= 0.75")
print(f"  mean horizontal run      {mean('mean_run', m):6.2f}   contract >= 5")
print(f"  single-cell runs         {mean('single_runs', m):6.3f}   contract < 0.33")
print()
print("=== INPUT RULE (one row) ===")
print(f"  ground hex / L           {r[0]['ground_hex']}  {mean('ground_L', r):6.3f}   Adam: flat single colour")
print(f"  lit fraction             {mean('lit_frac', r):6.3f}   Adam: 'dots scattered on it'")
print(f"  distinct lit tones       {mean('distinct_lit', r):6.1f}")
print(f"  distinct grounds across sessions {len({x['ground_hex'] for x in r})} / {len(SESSIONS)}")
