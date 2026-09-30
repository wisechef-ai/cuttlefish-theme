#!/usr/bin/env python3
"""Pixel check of the spike-12 mantle in a REAL terminal screenshot.

The widget (mantle.mjs) paints 2 rows of ▀ whose (fg, bg) rgb is known exactly from the raw SGR
log. In the PNG, the mantle band is every pixel row where most pixels are palette colours. Inside
that band's bounding box, any pixel that is NOT a palette colour is a seam, a gap, or an
anti-alias fringe: exactly the artefact a font-drawn (not terminal-drawn) block glyph produces.

    mantle_pixels.py SHOT.png SHOT.sgr [--cols 120 --rows 40]

Prints one line of metrics; exit 0 when the band is found and has 0 off-palette pixels and the
expected 4 half-cell pixel stripes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from PIL import Image

TOOL = Path(__file__).resolve().parents[2] / "capture_tui.py"
_spec = importlib.util.spec_from_file_location("capture_tui", TOOL)
ct = importlib.util.module_from_spec(_spec)
sys.modules["capture_tui"] = ct
_spec.loader.exec_module(ct)


def palette_from_sgr(data: bytes, cols: int, rows: int) -> set[tuple[int, int, int]]:
    payload, dims = ct.parse_script_log(data)
    if dims:
        cols, rows = dims
    model = ct.model_from_bytes(payload or data, cols, rows)
    pal: set[tuple[int, int, int]] = set()
    for y, line in enumerate(model.screen.display):
        if line.count("▀") >= cols - 2:
            for x in range(model.screen.columns):
                cell = model.cell(x, y)
                if cell.data == "▀":
                    pal.update(ct.cell_colors(cell))
    return pal


def measure(png: Path, palette: set[tuple[int, int, int]]) -> dict:
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    band_rows = [y for y in range(h) if sum(px[x, y] in palette for x in range(w)) > w * 0.5]
    if not band_rows:
        return {"found": False}
    y0, y1 = band_rows[0], band_rows[-1]
    cols_in = [x for x in range(w) if px[x, (y0 + y1) // 2] in palette]
    x0, x1 = cols_in[0], cols_in[-1]
    off = sum(1 for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if px[x, y] not in palette)
    contiguous = band_rows == list(range(y0, y1 + 1))
    # Half-cell stripes: runs of pixel rows that are identical along the whole band width.
    stripes, prev = 0, None
    for y in range(y0, y1 + 1):
        row = tuple(px[x, y] for x in range(x0, x1 + 1))
        if row != prev:
            stripes += 1
        prev = row
    seen = {px[x, y] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}
    return {"found": True, "band": (x0, y0, x1, y1), "height_px": y1 - y0 + 1, "contiguous": contiguous,
            "off_palette_px": off, "stripes": stripes, "colours_seen": len(seen & palette),
            "palette": len(palette)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("png", type=Path)
    p.add_argument("sgr", type=Path)
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--rows", type=int, default=40)
    a = p.parse_args(argv)
    pal = palette_from_sgr(a.sgr.read_bytes(), a.cols, a.rows)
    if not pal:
        print(f"{a.png.name}: FAIL no mantle rows in {a.sgr.name}")
        return 1
    m = measure(a.png, pal)
    ok = m.get("found") and m["off_palette_px"] == 0 and m["contiguous"] and m["stripes"] == 4
    print(f"{a.png.name}: {'PASS' if ok else 'FAIL'} {m}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
