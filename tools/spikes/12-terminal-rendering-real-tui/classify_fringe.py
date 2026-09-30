#!/usr/bin/env python3
"""Classify every off-palette pixel inside the mantle band of a screenshot.

    classify_fringe.py SHOT.png SHOT_OR_REF.sgr [--region x0,y0,x1,y1]

For each off-palette pixel, look at its nearest palette pixels up/down and left/right. If its rgb
lies between two such neighbours (per channel, inclusive), it is a BLEND: an anti-aliased edge
where two mantle colours meet (sub-pixel cell geometry). Otherwise it is a GAP: something that is
neither neighbour, e.g. the terminal background showing through a seam or a font glyph that does
not fill its cell. Prints counts and the rows/columns where each kind occurs (relative to the band).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mantle_pixels as mp  # noqa: E402


def between(p, a, b) -> bool:
    return all(min(x, y) - 2 <= v <= max(x, y) + 2 for v, x, y in zip(p, a, b))


def classify(png: Path, pal: set, region=None) -> dict:
    im = Image.open(png).convert("RGB")
    if region:
        im = im.crop(region)
    tmp = Path(tempfile.mkstemp(suffix=".png")[1])
    im.save(tmp)
    try:
        m = mp.measure(tmp, pal)
    finally:
        tmp.unlink()
    if not m.get("found"):
        return {"found": False}
    x0, y0, x1, y1 = m["band"]
    px = im.load()

    def near(x, y, dx, dy):
        for k in range(1, 4):
            xx, yy = x + dx * k, y + dy * k
            if x0 <= xx <= x1 and y0 <= yy <= y1 and px[xx, yy] in pal:
                return px[xx, yy]
        return None

    kinds, blend_rows, gap_rows, blend_cols = Counter(), Counter(), Counter(), Counter()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            p = px[x, y]
            if p in pal:
                continue
            u, d, l, r = near(x, y, 0, -1), near(x, y, 0, 1), near(x, y, -1, 0), near(x, y, 1, 0)
            if (u and d and between(p, u, d)) or (l and r and between(p, l, r)):
                kinds["blend"] += 1
                blend_rows[y - y0] += 1
                blend_cols[x - x0] += 1
            else:
                kinds["gap"] += 1
                gap_rows[y - y0] += 1
    return {"found": True, "band_px": (x1 - x0 + 1, y1 - y0 + 1), "off_palette": sum(kinds.values()),
            "blend": kinds["blend"], "gap": kinds["gap"], "blend_rows": dict(sorted(blend_rows.items())),
            "gap_rows": dict(sorted(gap_rows.items())), "blend_col_count": len(blend_cols)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("png", type=Path)
    p.add_argument("sgr", type=Path)
    p.add_argument("--region", type=lambda s: tuple(int(v) for v in s.split(",")))
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--rows", type=int, default=40)
    a = p.parse_args(argv)
    pal = mp.palette_from_sgr(a.sgr.read_bytes(), a.cols, a.rows)
    r = classify(a.png, pal, a.region)
    print(f"{a.png.name}: {r}")
    return 0 if r.get("found") and r["gap"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
