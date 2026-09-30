#!/usr/bin/env python3
"""cf2909 spike 15: objective seam/gradient metrics for a Terminator capture PNG.

    <python-with-Pillow> seam_metrics.py SHOT.png [...]

pattern.py prints, on a tall terminal, these rows starting at the first seam row:
  0 █..  1 █..  2 ▀..  3 ▄..  4 ▌▐..  5.. glyph rows ..  then 24-bit, 24b half,
  256, auto rung, Braille, Braille ⣿.
Measured per PNG (all in pixels, fg #d8d8d8 on bg #101014):
  cell_h/cell_w  cell_h = (█ █ ▀-top slab + dark gap + ▄-bottom) / 4 cells; cell_w = ▌▐ run
  gap_rows/cols  unlit lines inside the █ slab: any seam between tiled cells shows here
  half_fringe    pixel lines in the ▀ row that are partly lit (anti-aliasing) — 0 = exact edge
  comb_runs_px   lit/dark run widths along ▌▐ — a single value = crisp, AA-free half cells
  glyph_coverage_err_max  |lit area / cell area - geometric coverage| worst over all 15 glyphs
  rows           per colour row: (distinct colours, max per-step channel jump)
  --same A B     pixel-diff the block regions of two captures with the same cell size
                 (identical across fonts = the terminal, not the font, draws the glyphs)
"""
import sys
from PIL import Image

LIT = 200
GLYPHS = "▀▄█▌▐▖▗▘▝▚▞▙▛▜▟"  # pattern.py's BLOCKS, same order
COVERAGE = dict(zip(GLYPHS, [0.5, 0.5, 1, 0.5, 0.5, .25, .25, .25, .25, .5, .5, .75, .75, .75, .75]))

def lit(px):
    return min(px[:3]) >= LIT


def row_colours(p, y, x0, x1):
    seq = []
    for x in range(x0, x1 + 1):
        c = p[x, y]
        if not seq or seq[-1] != c:
            seq.append(c)
    jump = max((max(abs(a - b) for a, b in zip(c1, c2)) for c1, c2 in zip(seq, seq[1:])), default=0)
    return len(seq), jump


def analyse(path, _raw=False):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    p = im.load()
    top = next((y for y in range(H) if sum(lit(p[x, y]) for x in range(0, W, 4)) > 0.6 * W / 4), None)
    if top is None:
        raise SystemExit("%s: no tiled █ slab found (pattern not on screen?)" % path)
    xs = [x for x in range(W) if lit(p[x, top])]
    x0, x1 = xs[0], xs[-1]
    bot = top
    while bot + 1 < H and lit(p[(x0 + x1) // 2, bot + 1]):
        bot += 1
    # slab = █ █ + top half of ▀; then (▀ bottom + ▄ top) dark; then ▄ bottom lit.
    # Those three runs span exactly 4 cells, whatever way an odd cell height splits.
    mid = (x0 + x1) // 2
    y = bot + 1
    while y < H - 1 and not lit(p[mid, y]):
        y += 1

    # ▄ sits directly on the ▌▐ comb, so at a ▌ column the lit run continues:
    # take the shortest run over a span of columns (some are ▐-dark below).
    def run_end(x):
        yy = y
        while yy < H - 1 and lit(p[x, yy]):
            yy += 1
        return yy
    y2 = min(run_end(x) for x in range(x0, x0 + 60))
    ch = (y2 - top) / 4
    gap_rows = sum(1 for y in range(top, bot + 1) if not all(lit(p[x, y]) for x in range(x0, x1 + 1)))
    gap_cols = sum(1 for x in range(x0, x1 + 1) if not all(lit(p[x, y]) for y in range(top, bot + 1)))
    # ▀ row (row 2): lit fraction for each pixel line; any line strictly between 0 and 1 = AA fringe
    r2 = round(top + 2 * ch)
    half = [sum(lit(p[x, y]) for x in range(x0, x1 + 1)) / (x1 - x0 + 1) for y in range(r2, round(r2 + ch))]
    fringe_lines = sum(1 for f in half if 0.02 < f < 0.98)
    # ▌▐ comb (row 4), sampled mid-cell
    yc = round(top + 4.5 * ch)
    edges = [x for x in range(x0, x1) if lit(p[x, yc]) != lit(p[x + 1, yc])]
    runs = sorted({b - a for a, b in zip(edges, edges[1:])})
    # colour rows: saturated bands below the comb
    def sat(c):
        return max(c) - min(c)
    ys = [y for y in range(yc, H) if sat(p[x0 + 3, y]) > 100]
    bands = []
    for y in ys:
        if bands and y == bands[-1][1] + 1:
            bands[-1][1] = y
        else:
            bands.append([y, y])
    gy0 = bands[0][0]  # first colour row = 24-bit
    out = {}
    for i, name in enumerate(["24-bit", "24b half(top)", "256", "auto"]):
        y = round(gy0 + (i + (0.25 if i == 1 else 0.5)) * ch)
        out[name] = row_colours(p, y, x0, x1)
    # Glyph cells: 'U+XXXX gg' = 10 columns incl. separator, 14 per row at 155 cols;
    # the doubled glyph sits at columns 7-8. Lit area / doubled-cell area must equal
    # the glyph's geometric coverage exactly if the terminal draws it as geometry.
    cw = runs[0]  # ▌▐ comb: each lit/dark run is ½+½ cell = exactly one cell width
    cov_err, boxes = {}, [(x0, top, x1 + 1, round(top + 5 * ch))]  # the 5 seam rows
    for k, g in enumerate(GLYPHS):
        row, col = divmod(k, 14)
        gx = round(x0 + (col * 10 + 7) * cw)
        cy0, cy1 = round(top + (5 + row) * ch), round(top + (6 + row) * ch)
        area = 2 * cw * (cy1 - cy0)
        litpx = sum(1 for x in range(gx, gx + 2 * cw) for y in range(cy0, cy1) if lit(p[x, y]))
        cov_err[g] = round(litpx / area - COVERAGE[g], 3)
        boxes.append((gx, cy0, gx + 2 * cw, cy1))
    if _raw:
        return {"cw": cw, "ch": ch, "block_boxes": boxes}
    return {
        "png": path.rsplit("/", 1)[-1], "cell_h": round(ch, 2), "cell_w": cw,
        "glyph_coverage_err_max": max(abs(v) for v in cov_err.values()),
        "gap_rows": gap_rows, "gap_cols": gap_cols,
        "half_fringe_lines": fringe_lines, "comb_runs_px": runs,
        "rows(distinct,max_jump)": out,
    }


def same_blocks(pa, pb):
    """Pixel-diff the pure-block rows (seams + doubled glyph runs) of two captures
    that share a cell size: identical pixels across fonts = the terminal, not the
    font, draws the glyphs."""
    from PIL import ImageChops
    ra, rb = analyse(pa, _raw=True), analyse(pb, _raw=True)
    if (ra["cw"], ra["ch"]) != (rb["cw"], rb["ch"]):
        return "cell sizes differ (%s vs %s); use glyph_coverage_err instead" % (
            (ra["cw"], ra["ch"]), (rb["cw"], rb["ch"]))
    boxes_a, boxes_b = ra["block_boxes"], rb["block_boxes"]
    ia, ib = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
    diffs = sum(1 for ba, bb in zip(boxes_a, boxes_b)
                if ImageChops.difference(ia.crop(ba), ib.crop(bb)).getbbox() is not None)
    return "%d/%d block regions differ" % (diffs, len(boxes_a))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--same"]:
        print(same_blocks(sys.argv[2], sys.argv[3]))
        sys.exit(0)
    for f in sys.argv[1:]:
        print(analyse(f))
