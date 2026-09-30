#!/usr/bin/env python3
"""cf2909 spike 15 test pattern: block elements, colour depth, Braille.

This is the one fixture every spike-15 matrix cell draws (Terminator/iTerm2,
local and over SSH, several fonts). All matrix cells therefore show the same
pixels, which is what makes their screenshots comparable.

    python3 tools/spikes/15-block-elements-colordepth/pattern.py [--depth D] [--cols N] [--lines N]

Stdlib only and deterministic: the same COLUMNS/LINES/TERM/COLORTERM always
produce the same bytes. It needs Python 3.8+ (mac01 ships 3.9) and never
reads or writes HERMES_HOME, so it is safe to run under a throwaway one.

Every row starts with an on-screen label, so a screenshot describes itself:
  header    TERM / COLORTERM / size / detected colour depth
  glyphs    each block glyph with its codepoint, then a doubled run of it
  seams     tiled full blocks and half blocks (gaps show up as lines)
  24-bit    hue sweep, SGR 38;2 truecolor fg (always emitted: it IS the probe)
  24b half  the same sweep as a half block, 38;2 fg + 48;2 bg (mantle primitive)
  256       the same sweep quantised to xterm-256, SGR 38;5 (fallback rung)
  auto rung the sweep at the DETECTED depth: this is how graceful degradation
            looks, and it never emits 38;2 unless truecolor is advertised
  Braille   dot patterns for comparison (font-dependent; the opt-in look)
"""
from __future__ import annotations

import argparse
import colorsys
import os
import shutil
import sys

# The D4 primitive set, in the order the plan lists it.
BLOCKS = "▀▄█▌▐▖▗▘▝▚▞▙▛▜▟"
# Braille: single dots building up to the full cell, then some textures.
BRAILLE = "⠁⠃⠇⡇⡏⡟⡿⣿⣷⣯⣟⡿⢿⣻⣽⣾⠿⠛⠉⣀⣤⣶"

RESET = "\x1b[0m"
DIM = "\x1b[2m"
LABEL_W = 11  # row labels are padded to this many columns

CUBE = (0, 95, 135, 175, 215, 255)
ANSI16 = (
    (0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
    (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
    (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)


# ── colour depth ─────────────────────────────────────────────────────────────
def detect_depth(env) -> str:
    """What the terminal advertises. Returns truecolor | 256 | 16."""
    colorterm = env.get("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return "truecolor"
    term = env.get("TERM", "").lower()
    if "direct" in term:
        return "truecolor"
    if "256" in term:
        return "256"
    return "16"


def _dist(a, b) -> int:
    return sum((x - y) * (x - y) for x, y in zip(a, b))


def to_256(rgb) -> int:
    """Nearest xterm-256 index (6x6x6 cube or the 24-step grey ramp)."""
    idx = [min(range(6), key=lambda i: abs(CUBE[i] - c)) for c in rgb]
    cube_rgb = tuple(CUBE[i] for i in idx)
    cube_i = 16 + 36 * idx[0] + 6 * idx[1] + idx[2]
    grey = max(0, min(23, round((sum(rgb) / 3 - 8) / 10)))
    grey_v = 8 + 10 * grey
    if _dist(rgb, (grey_v,) * 3) < _dist(rgb, cube_rgb):
        return 232 + grey
    return cube_i


def to_16(rgb) -> int:
    return min(range(16), key=lambda i: _dist(rgb, ANSI16[i]))


def fg(rgb, depth: str) -> str:
    if depth == "truecolor":
        return "\x1b[38;2;%d;%d;%dm" % rgb
    if depth == "256":
        return "\x1b[38;5;%dm" % to_256(rgb)
    i = to_16(rgb)
    return "\x1b[%dm" % (30 + i if i < 8 else 90 + i - 8)


def bg(rgb, depth: str) -> str:
    if depth == "truecolor":
        return "\x1b[48;2;%d;%d;%dm" % rgb
    if depth == "256":
        return "\x1b[48;5;%dm" % to_256(rgb)
    i = to_16(rgb)
    return "\x1b[%dm" % (40 + i if i < 8 else 100 + i - 8)


def hue(i: int, n: int, value: float = 1.0):
    r, g, b = colorsys.hsv_to_rgb(i / max(1, n), 1.0, value)
    return (round(r * 255), round(g * 255), round(b * 255))


# ── rows ─────────────────────────────────────────────────────────────────────
def label(text: str) -> str:
    return DIM + text.ljust(LABEL_W)[:LABEL_W] + RESET


def fit(text: str, cols: int) -> str:
    """Plain (SGR-free) text clipped to the terminal width."""
    return text if len(text) <= cols else text[: max(0, cols - 1)] + "…"


def glyph_rows(cols: int) -> list:
    """Each glyph as 'U+2580 ▀▀', packed into as many rows as the width needs."""
    cells = ["U+%04X %s%s" % (ord(g), g, g) for g in BLOCKS]
    avail = max(len(cells[0]), cols - LABEL_W)  # one cell always fits at cols>=20
    rows, cur = [], ""
    for cell in cells:
        piece = (" " if cur else "") + cell
        if cur and len(cur) + len(piece) > avail:
            rows.append(cur)
            cur = cell
        else:
            cur += piece
    rows.append(cur)
    return [label("glyphs" if n == 0 else "") + row for n, row in enumerate(rows)]


def seam_rows(cols: int) -> list:
    """Tiles that expose gaps: two rows of █, a ▀ row over a ▄ row, ▌▐ pairs."""
    w = max(1, cols - LABEL_W)
    return [
        label("seams █") + "█" * w,
        label("") + "█" * w,
        label("seams ▀▄") + "▀" * w,
        label("") + "▄" * w,
        label("seams ▌▐") + "▌▐" * (w // 2) + ("▌" if w % 2 else ""),
    ]


def gradient_row(name: str, cols: int, depth: str) -> str:
    w = max(1, cols - LABEL_W)
    return label(name) + "".join(fg(hue(i, w), depth) + "█" for i in range(w)) + RESET


def half_gradient_row(name: str, cols: int, depth: str) -> str:
    """▀ with the sweep on top (fg) and a darker sweep below (bg)."""
    w = max(1, cols - LABEL_W)
    body = "".join(fg(hue(i, w), depth) + bg(hue(i, w, 0.45), depth) + "▀" for i in range(w))
    return label(name) + body + RESET


def braille_rows(cols: int, depth: str) -> list:
    w = max(1, cols - LABEL_W)
    plain = (BRAILLE * (w // len(BRAILLE) + 1))[:w]
    coloured = "".join(fg(hue(i, w), depth) + "⣿" for i in range(w))
    return [label("Braille") + plain, label("Braille ⣿") + coloured + RESET]


def render(env, cols: int, lines: int, depth_override: str = "auto") -> str:
    detected = detect_depth(env)
    depth = detected if depth_override == "auto" else depth_override
    header = [
        "cf2909 spike 15 — block elements / colour depth probe",
        "TERM=%s COLORTERM=%s" % (env.get("TERM", "(unset)"), env.get("COLORTERM", "(unset)")),
        "size=%dx%d detected depth: %s auto rung uses: %s" % (cols, lines, detected, depth),
    ]
    probe = glyph_rows(cols) + [
        gradient_row("24-bit", cols, "truecolor"),
        half_gradient_row("24b half", cols, "truecolor"),
        gradient_row("256", cols, "256"),
        gradient_row("auto rung", cols, depth),
    ] + braille_rows(cols, depth)
    seams = seam_rows(cols)
    # Honour the height: the seam tiles go first on a short terminal; the
    # labelled probe rows always print (a screenshot needs them).
    out = [fit(h, cols) for h in header]
    if len(header) + len(probe) + len(seams) <= lines - 1:  # keep a prompt row
        out += seams
    out += probe
    return "\n".join(out) + RESET + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cf2909 spike 15 block/colour test pattern")
    ap.add_argument("--depth", choices=("auto", "truecolor", "256", "16"), default="auto",
                    help="colour depth for the 'auto rung' row (default: detect from env)")
    ap.add_argument("--cols", type=int, help="override the detected width")
    ap.add_argument("--lines", type=int, help="override the detected height")
    args = ap.parse_args(argv)
    size = shutil.get_terminal_size((80, 24))  # honours COLUMNS/LINES first
    cols = max(20, args.cols or size.columns)
    lines = max(5, args.lines or size.lines)
    sys.stdout.write(render(os.environ, cols, lines, args.depth))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
