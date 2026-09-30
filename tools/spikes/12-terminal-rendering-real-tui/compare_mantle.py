#!/usr/bin/env python3
"""Compare the mantle rows of two raw SGR logs (e.g. truecolor vs 256-colour captures).

Replays each log through capture_tui's screen model, finds the two full-width ▀ rows, and
compares every cell's resolved (fg, bg) rgb. Exit 0 when identical, 1 with a diff otherwise.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "capture_tui.py"
_spec = importlib.util.spec_from_file_location("capture_tui", TOOL)
ct = importlib.util.module_from_spec(_spec)
sys.modules["capture_tui"] = ct
_spec.loader.exec_module(ct)


def mantle_cells(model, min_run: int):
    rows = [y for y, line in enumerate(model.screen.display) if line.count("▀") >= min_run]
    return rows, [[ct.cell_colors(model.cell(x, y)) for x in range(model.screen.columns)
                   if model.cell(x, y).data == "▀"] for y in rows]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--rows", type=int, default=40)
    args = p.parse_args(argv)
    min_run = args.cols - 2
    ra, ca = mantle_cells(ct.model_from_bytes(args.a.read_bytes(), args.cols, args.rows), min_run)
    rb, cb = mantle_cells(ct.model_from_bytes(args.b.read_bytes(), args.cols, args.rows), min_run)
    print(f"{args.a.name}: mantle rows {ra}; {args.b.name}: mantle rows {rb}")
    if len(ca) != 2 or len(cb) != 2:
        print("FAIL: expected exactly 2 mantle rows in each capture")
        return 1
    diffs = [(r, x, ca[r][x], cb[r][x]) for r in range(2) for x in range(min(len(ca[r]), len(cb[r])))
             if ca[r][x] != cb[r][x]]
    if diffs or [len(r) for r in ca] != [len(r) for r in cb]:
        print(f"FAIL: {len(diffs)} differing cells, widths {[len(r) for r in ca]} vs {[len(r) for r in cb]}")
        for d in diffs[:10]:
            print("  row %d col %d: %s vs %s" % d)
        return 1
    colours = sorted({c for row in ca for cell in row for c in cell})
    print(f"IDENTICAL: 2 rows x {len(ca[0])} cells, {len(colours)} distinct rgb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
