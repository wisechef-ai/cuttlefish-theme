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
import functools
import hashlib
import math
import os
import shutil
import signal
import sys
import time

# ---------------------------------------------------------------- colour (OKLCh)


def _oklab_to_srgb(L: float, a: float, b: float) -> tuple[int, int, int]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )

    def enc(c: float) -> int:
        c = min(1.0, max(0.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(c * 255)

    return enc(rgb[0]), enc(rgb[1]), enc(rgb[2])


def oklch(L: float, C: float, h_deg: float) -> tuple[int, int, int]:
    h = math.radians(h_deg)
    return _oklab_to_srgb(L, C * math.cos(h), C * math.sin(h))


AMBER_H, RED_H = 72.0, 27.0
TIER_L = (0.58, 0.66, 0.74)  # v22 frozen tokens: three lightness steps = separate organs
TIER_C = 0.135

# ---------------------------------------------------------------- determinism


@functools.lru_cache(maxsize=1 << 16)  # lattice/burst seeds repeat every frame
def _h(*parts: object) -> float:
    """Deterministic uniform [0,1) from any parts (blake2b, never Python's hash())."""
    d = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(d, "big") / 2 ** 64


def session_hue(session: str) -> float:
    return 110.0 + 230.0 * _h("hue", session)  # arc [110, 340): never amber/red


# ---------------------------------------------------------------- the organs


class Organ:
    __slots__ = ("x", "y", "tier", "phase", "rate", "alarm", "e")

    def __init__(self, x: int, y: int, tier: int, phase: float, rate: float, alarm: float):
        self.x, self.y, self.tier = x, y, tier
        self.phase, self.rate, self.alarm = phase, rate, alarm
        self.e = 0.0  # displayed expansion, 0..1 (lags the drive asymmetrically)


def constellation(session: str, cols: int, rows: int, density: float) -> list[Organ]:
    """Blue-noise-ish scatter: one candidate per cell, kept with p=density, then thinned
    so no two organs touch horizontally (touching discs read as a blob, not a skin)."""
    out: list[Organ] = []
    taken: set[tuple[int, int]] = set()
    for y in range(rows):
        for x in range(cols):
            if _h("pos", session, x, y) >= density:
                continue
            if any((x + dx, y + dy) in taken for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue  # Poisson-ish: organs never touch, so each reads as one organ
            taken.add((x, y))
            r = _h("tier", session, x, y)
            tier = 0 if r < 0.45 else 1 if r < 0.8 else 2  # dark organs commonest, as in Sepia
            out.append(Organ(x, y, tier, _h("ph", session, x, y), 0.7 + 0.6 * _h("rt", session, x, y),
                             _h("alarm", session, x, y)))
    return out


# ---------------------------------------------------------------- neural drive per state


def _bump(dt: float, rise: float, fall: float) -> float:
    """A single twitch: 0 before, fast attack, exponential release."""
    if dt < 0:
        return 0.0
    if dt < rise:
        return dt / rise
    return math.exp(-(dt - rise) / fall)


def vnoise(x: float, y: float, seed: str = "n") -> float:
    """Smooth 2-D value noise in [0,1] -- spatially coherent, so neighbours act together."""
    xi, yi = math.floor(x), math.floor(y)
    fx, fy = x - xi, y - yi
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _h(seed, xi, yi), _h(seed, xi + 1, yi)
    c, d = _h(seed, xi, yi + 1), _h(seed, xi + 1, yi + 1)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


BURST_EVERY = 0.25


@functools.lru_cache(maxsize=8)  # one burst list per tick, shared by every organ
def _bursts(k0: int, cols: int, rows: int) -> tuple[tuple[float, float, float, float], ...]:
    per_tick = max(1, round(cols * rows / 650))  # same sparkle rate per area at any size
    return tuple((_h("bx", k, j) * cols, _h("by", k, j) * rows, 5 + 7 * _h("br", k, j), k * BURST_EVERY)
                 for k in range(k0 - 4, k0 + 1) for j in range(per_tick))


def drive(o: Organ, state: str, t: float, ts: float, cols: int, rows: int) -> tuple[float, str]:
    """Target expansion 0..1 and pigment class ('id' | 'amber' | 'red') for one organ.
    t = wall time, ts = time since entering the state."""
    tonic = (0.26, 0.32, 0.48)[o.tier]  # resting tone: '·' and a few dim '•', never dust

    if state == "idle":
        # Rare individual twitches. Each organ owns a slow private clock; a twitch fires
        # when its window comes up AND a seeded coin says so -> ~1 organ / 1.5 s overall.
        period = 9.0 / o.rate
        k = math.floor((t + o.phase * period) / period)
        if _h("tw", o.x, o.y, k) < 0.18:
            start = k * period - o.phase * period + _h("tws", o.x, o.y, k) * period * 0.5
            return min(1.0, tonic + 0.6 * _bump(t - start, 0.12, 0.9)), "id"
        return tonic, "id"

    if state == "thinking":
        # Passing cloud: exactly one broad raised-cosine band visible at a time, drifting
        # left->right, with a faint second harmonic so it never looks like a scanner.
        # Clouds are blobs of coherent noise advected left->right (~6 s per crossing),
        # thresholded softly: patchy, off-axis, never a full-height scanner column.
        # On a 2-row strip this degenerates gracefully into a drifting band.
        u = o.x / max(6.0, cols / 9.0) - t * 1.5
        v = o.y / max(2.0, rows / 3.5)
        n = 0.65 * vnoise(u, v, "c1") + 0.35 * vnoise(2.1 * u + 7, 2.1 * v, "c2")
        cloud = min(1.0, max(0.0, (n - 0.48) / 0.22))
        cloud = cloud * cloud * (3 - 2 * cloud)
        return 0.24 + 0.72 * cloud, "id"

    if state == "tool":
        # Sparkle bursts: every 0.45 s a new seeded focus; organs near it flash open in
        # order of distance (a ripple), then relax elastically.
        level = 0.25
        for cx, cy, radius, start in _bursts(math.floor(t / BURST_EVERY), cols, rows):
            dx = (o.x - cx) / 2.0  # cells are ~2:1 tall
            if abs(dx) > radius:
                continue
            dist = math.hypot(dx, o.y - cy)
            if dist > radius:
                continue
            onset = start + dist * 0.035
            level = max(level, 0.95 * (1 - dist / radius) ** 0.5 * _bump(t - onset, 0.08, 0.45))
        # The brightest moment of a flash shows the iridophore layer beneath: a pale
        # glint, so tool bursts are crisp and cool where thinking is soft and pigmented.
        return min(1.0, level), ("glint" if level > 0.70 else "id")

    if state == "needs-you":
        # Identity organs settle low and hold; a few seeded organs become amber eyespots
        # that pulse together at 0.5 Hz -- synchronous = "this is a signal, not activity".
        if o.alarm < 0.06:
            pulse = 0.5 * (1 + math.sin(2 * math.pi * 0.5 * t))
            return 0.55 + 0.45 * pulse, "amber"
        return 0.26, "id"

    if state == "fault":
        # Deimatic blanch: everything shuts fast (handled by the 0.10 s/0.55 s kinetics),
        # then after 0.6 s a sparse margin of red organs flushes open and holds. Static.
        if o.alarm < 0.10 and ts > 0.6:
            return 0.8, "red"
        return 0.0, "id"

    raise ValueError(state)


# ---------------------------------------------------------------- appearance

GLYPHS = " ·•●"


E_STEPS = 10  # perceptual steps of expansion; finer changes are invisible, so never sent


@functools.lru_cache(maxsize=4096)
def _paint(tier: int, q: int, pigment: str, hue: float) -> tuple[str, tuple[int, int, int] | None]:
    return _appearance(tier, q / E_STEPS, pigment, hue)


def appearance(o: Organ, e: float, pigment: str, hue: float) -> tuple[str, tuple[int, int, int] | None]:
    """Quantised + memoised: an organ costs a terminal write only when it visibly changes."""
    return _paint(o.tier, round(e * E_STEPS), pigment, hue)


def _appearance(tier: int, e: float, pigment: str, hue: float) -> tuple[str, tuple[int, int, int] | None]:
    if e < 0.12:
        return " ", None
    g = GLYPHS[1 if e < 0.42 else 2 if e < 0.72 else 3]
    if pigment == "amber":
        return g, oklch(0.84 * (0.80 + 0.20 * e), 0.165, AMBER_H)
    if pigment == "red":
        return g, oklch(0.71 * (0.82 + 0.18 * e), 0.215, RED_H)
    if pigment == "glint":
        return g, oklch(0.90, 0.05, hue - 25.0)
    h = hue + (tier - 1) * 7.0  # tiers differ slightly in hue as well as lightness
    # Pigment spread: a half-open sac shows less, and less saturated, pigment -- but a
    # resting organ is still a deliberate dim point, not dust (L floor ~0.45).
    L = TIER_L[tier] * (0.80 + 0.28 * e)
    return g, oklch(min(0.86, L), TIER_C * (0.45 + 0.75 * e), h)


def step_kinetics(o: Organ, target: float, dt: float) -> None:
    tau = 0.10 if target > o.e else 0.55  # muscle opens fast, elastic sac closes slow
    o.e += (target - o.e) * (1 - math.exp(-dt / tau))


# ---------------------------------------------------------------- terminal renderer

CYCLE = [("idle", 6.0), ("thinking", 7.0), ("tool", 5.0), ("thinking", 4.0),
         ("needs-you", 6.0), ("fault", 5.0), ("idle", 4.0)]
FPS = {"idle": 4, "thinking": 10, "tool": 10, "needs-you": 8, "fault": 6}

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
