#!/usr/bin/env python3
"""Spike 02: full-width 1/2-row dock-top card follows pty resize. One command: run.py [outdir]"""
import sys, os, json, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_lib")); sys.path.insert(0, os.path.join(HERE, "..", "..", "capture"))
from tui import Tui, make_home
from pty_to_png import render_png
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-02"
os.makedirs(out, exist_ok=True)
home = make_home()
shutil.copy(f"{HERE}/band.mjs", f"{home}/tui-widgets/band.mjs")
open(f"{home}/band-rows", "w").write("2")
t = Tui(home, 120, 40)

cols_now = lambda: t.cols

def band_rows():
    """rows (index) whose cells are █/▄ painted with a non-default fg, and the extent [first,last] col."""
    res = []
    for y in range(t.rows):
        line = t.screen.buffer[y]
        xs = [x for x in range(t.cols) if line[x].data in "█▄" and line[x].fg not in ("default",)]
        if len(xs) >= cols_now() - 10:
            res.append((y, xs[0], xs[-1], len(xs)))
    return res

t.wait_for("█", 150); t.pump(2)
results = []
def measure(label, cols, rows):
    if (cols, rows) != (t.cols, t.rows):
        t.resize(cols, rows); t.pump(2.5)
    br = band_rows()
    ok = len(br) == int(open(f"{home}/band-rows").read()) and all(r[1] == 1 and r[2] == cols - 2 and r[3] == cols - 2 for r in br)
    # observed: card of width cols-2 occupies x=1..cols-2 (1 blank col each side); pass = full width + symmetric margin
    results.append({"label": label, "cols": cols, "rows": rows, "band_rows": br, "full_width_ok": ok})
    print(label, cols, rows, br, "OK" if ok else "MISMATCH")
    return br
measure("2row-120x40", 120, 40)
render_png(t.screen, f"{out}/02-2row-120x40.png")
for cols, rows in [(80, 24), (200, 40), (120, 24)]:
    measure(f"2row-{cols}x{rows}", cols, rows)
    if cols == 200: render_png(t.screen, f"{out}/02-2row-200x40.png")
    if cols == 80: render_png(t.screen, f"{out}/02-2row-80x24.png")
# 1 row: rewrite the rows file, then force re-render by resizing (widget reads rows on render)
open(f"{home}/band-rows", "w").write("1")
t.resize(121, 40); t.pump(1.5); t.resize(120, 40); t.pump(2.5)
measure("1row-120x40", 120, 40)
render_png(t.screen, f"{out}/02-1row-120x40.png")
json.dump(results, open(f"{out}/results.json", "w"), indent=1)
t.close(); shutil.rmtree(home, ignore_errors=True)
print("ALL_OK", all(r["full_width_ok"] for r in results))
