#!/usr/bin/env python3
"""Sparse chromatophore dots -- a look-and-feel preview (Adam, 2026-10-21).

    "instead of complete background change, simple dots in random places (pixels)
     that change colour, mimicking the real mantle/cuttlefish colour behaviour based
     on the agent execution/state -- lightweight but visually nice"

What this changes vs. what ships today
--------------------------------------
* NO background change. Nothing here emits a background SGR or OSC 11: every dot is a
  foreground glyph on whatever ground your terminal already has.
* Dots are SPARSE and FIXED IN PLACE. A real chromatophore does not move; it is an
  elastic pigment sac pulled open by radial muscles. Positions are seeded per session
  (blake2b), so a window keeps its constellation; ~10% of cells hold an organ.
* An organ changes appearance by EXPANDING, not by changing pigment. So "colour change"
  is mostly area + saturation: retracted -> invisible pinpoint, open -> a full disc.
  Glyph ladder:  ' '  ·  •  ●   with lightness/chroma rising with expansion.
* Hue = which session (OKLCh arc 110-340 deg, never amber or red). State = what the
  organs DO, never the identity hue -- except the two alarms, which add amber / red
  organs on top (eyespots / margin flush), as in v22.
* Asymmetric kinetics: opening is muscular and fast (tau 0.10 s), closing is elastic
  and slower (tau 0.55 s). That one asymmetry is most of why it reads as alive.

States (from real Hermes hooks when wired):
    idle       rare twinkles: one organ flickers every ~1.5 s, the rest hold   (~0 cost)
    thinking   passing clouds: soft blobs of expansion drift across the skin  (pre_llm_call)
    tool       sparkle bursts: local clusters flash open with a pale iridophore
               glint at the peak, relax, repeat                                 (pre_tool_call)
    needs-you  identity organs settle low; 3 amber eyespots pulse together      (clarify/approval)
    fault      blanch: every organ shuts in 0.4 s, then a few red organs flush  (api_request_error)

Run (in a real truecolor terminal):
    python3 tools/dots_preview.py                 # strip above a fake prompt, cycles states
    python3 tools/dots_preview.py --field         # whole window = the desktop-backdrop look
    python3 tools/dots_preview.py --state tool    # hold one state
    python3 tools/dots_preview.py --session work  # another session's hue + constellation
    python3 tools/dots_preview.py --png out.png --state thinking --t 3.2   # still frame

Cost: diff rendering + quantised expansion (10 steps) -- an organ costs a terminal write
only when it VISIBLY changes. Measured on a 120x30 pty, 10 s per state (2026-10-21):

    strip (2 rows, 19 organs)   idle 8 cells/s, 0.6 KB/s | working 55-66 cells/s, <3 KB/s | ~2% CPU
    field (whole window, 259)   idle 95 cells/s, 3 KB/s  | working ~800 cells/s, 26 KB/s | 6-9% CPU

CPU includes the Python interpreter and the 10 fps status label; a production renderer
would live in the TUI/desktop TS core and animate only while the agent works.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import sys
import time
from pathlib import Path

# The model (organs, drive, kinetics, appearance) lives in python/domain/dots.py -- the oracle the
# TS core is tested against. This file is only the terminal + PNG adapter around it. Loaded by path:
# the repo root is not an importable package name (it is `cuttlefish-theme`).
_DOTS = Path(__file__).resolve().parents[1] / "python" / "domain" / "dots.py"
_spec = importlib.util.spec_from_file_location("cuttlefish_dots_domain", _DOTS)
assert _spec and _spec.loader
_dots = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("cuttlefish_dots_domain", _dots)
_spec.loader.exec_module(_dots)

Organ = _dots.Organ
constellation = _dots.constellation
drive = _dots.drive
appearance = _dots.appearance
step_kinetics = _dots.step_kinetics
session_hue = _dots.session_hue
oklch = _dots.oklch
vnoise = _dots.vnoise
FPS = _dots.FPS
GLYPHS = _dots.GLYPHS
E_STEPS = _dots.E_STEPS

# ---------------------------------------------------------------- terminal renderer

CYCLE = [("idle", 6.0), ("thinking", 7.0), ("tool", 5.0), ("thinking", 4.0), ("review", 4.0),
         ("needs-you", 6.0), ("fault", 5.0), ("unknown", 3.0), ("idle", 4.0)]

FAKE = [
    "\x1b[2m you ›\x1b[0m refactor the session reducer and run the suite",
    "",
    "\x1b[2m hermes ›\x1b[0m Reading packages/core/domain/state-hook.ts ...",
    "   ✓ 138 passed, 0 failed (4.1s)",
    "",
]


def _interrupt(*_: object) -> None:
    raise KeyboardInterrupt


def run_terminal(args: argparse.Namespace) -> None:
    out = sys.stdout
    cols, rows_total = shutil.get_terminal_size((100, 30))
    if args.field:
        top, rows = 0, rows_total - 1
    else:
        rows = args.rows
        top = rows_total - rows - 3

    # The handler only RAISES; the terminal is restored in one `finally`. Writing from
    # the handler re-enters stdout's buffer when the signal lands mid-frame.
    signal.signal(signal.SIGTERM, _interrupt)
    out.write("\x1b[?1049h\x1b[?25l\x1b[2J")  # alt screen; NO background is ever set
    try:
        _loop(args, out, cols, rows_total, rows, top)
    except KeyboardInterrupt:
        pass
    finally:
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()


def _loop(args: argparse.Namespace, out, cols: int, rows_total: int, rows: int, top: int) -> None:
    hue = session_hue(args.session)
    organs = constellation(args.session, cols, rows, args.density)
    prev: dict[tuple[int, int], tuple[str, object]] = {}
    if not args.field:
        for i, line in enumerate(FAKE):
            out.write(f"\x1b[{max(1, top - len(FAKE) + i)};1H{line}")
        out.write(f"\x1b[{rows_total - 1};1H\x1b[2m{'─' * cols}\x1b[0m")
    t0 = last = time.monotonic()
    state, entered = "", t0
    cells_written = 0
    while True:
        now = time.monotonic()
        t = now - t0
        if args.state:
            want = args.state
        else:
            total = sum(d for _, d in CYCLE)
            tt, want = t % total, CYCLE[0][0]
            for name, d in CYCLE:
                if tt < d:
                    want = name
                    break
                tt -= d
        if want != state:
            state, entered = want, now
        dt, last = now - last, now
        frame: list[str] = []
        for o in organs:
            target, pig = drive(o, state, t, now - entered, cols, rows)
            step_kinetics(o, target, dt)
            cell = appearance(o, o.e, pig, hue)
            if prev.get((o.x, o.y)) != cell:
                prev[(o.x, o.y)] = cell
                g, rgb = cell
                sgr = f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m" if rgb else ""
                frame.append(f"\x1b[{top + o.y + 1};{o.x + 1}H{sgr}{g}\x1b[39m")
        cells_written += len(frame)
        label = f" {state:<9}  organs {len(organs)}  cells/s {cells_written / max(t, 1e-3):5.1f} "
        frame.append(f"\x1b[{rows_total};1H\x1b[2m{label}  ctrl-c to quit\x1b[0m\x1b[K")
        out.write("".join(frame))
        out.flush()
        time.sleep(1.0 / FPS[state])


# ---------------------------------------------------------------- PNG still (for review without a tty)


def run_png(args: argparse.Namespace) -> None:
    from PIL import Image, ImageDraw, ImageFont

    cols, rows = args.cols, (args.rows if not args.field else 24)
    cw, ch = 9, 18
    bg = tuple(int(args.bg[i:i + 2], 16) for i in (1, 3, 5))
    hue = session_hue(args.session)
    organs = constellation(args.session, cols, rows, args.density)
    # Simulate kinetics from state entry up to t, at the live frame rate.
    fps = FPS[args.state]
    n = max(1, int(args.t * fps))
    for i in range(n + 1):
        tt = 1000.0 + i / fps  # arbitrary wall clock; ts = i/fps
        for o in organs:
            target, _ = drive(o, args.state, tt, i / fps, cols, rows)
            step_kinetics(o, target, 1 / fps)
    img = Image.new("RGB", (cols * cw, rows * ch), bg)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 15)
    for o in organs:
        _, pig = drive(o, args.state, 1000.0 + n / fps, n / fps, cols, rows)
        g, rgb = appearance(o, o.e, pig, hue)
        if rgb:
            d.text((o.x * cw, o.y * ch), g, fill=rgb, font=font)
    img.save(args.png)
    print(f"{args.png}: {args.state} t={args.t}s organs={len(organs)} hue={hue:.0f}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", choices=list(FPS))
    p.add_argument("--session", default="tori-demo")
    p.add_argument("--field", action="store_true", help="whole window (desktop-backdrop look)")
    p.add_argument("--rows", type=int, default=2, help="strip height in text rows")
    p.add_argument("--density", type=float, default=0.10)
    p.add_argument("--png")
    p.add_argument("--t", type=float, default=3.0)
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--bg", default="#1e1e1e", help="PNG only: stand-in for your terminal ground")
    a = p.parse_args()
    if a.png:
        a.state = a.state or "thinking"
        run_png(a)
    else:
        if not os.isatty(1):
            sys.exit("needs a real terminal (or use --png)")
        run_terminal(a)


if __name__ == "__main__":
    main()
