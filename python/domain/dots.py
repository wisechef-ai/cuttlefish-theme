"""D2 "scatter" -- the sparse chromatophore grammar (CONTEXT-D2 section 0). THE ORACLE.

Lifted from tools/dots_preview.py (feat/sparse-dots-preview 4ceb130 + aa3c671). The TS core
(packages/core/domain/pattern.ts + motion.ts) must match this module byte-for-byte on
packages/core/fixtures/dots-vectors.json (tools/gen-dots-vectors.py writes it, CI re-checks it).

PURE: no I/O, no clock, no randomness. Time (``t``, ``ts``, ``entered``) and the session seed are
arguments; every "random" number is a blake2b hash of its arguments. Float maths is chosen so that
CPython and V8 agree bit-for-bit: sqrt (never hypot / pow), round-half-up (never banker's round),
and no ``hash()``.

Grammar
-------
* organs  ~10 % of cells are candidates, thinned so no two of the 8 neighbours are both organs.
          Positions come from the seed and never move. Tiers 45/35/20 % at L .58/.66/.74, C .135,
          tier hue offsets -7/0/+7 deg.
* hue     identity = the arc [110, 340); never amber or red. Injected (the core allocator picks it).
* look    expansion e in [0,1], quantised to 10 steps; glyph ladder ' ' . o O; foreground only.
* kinetic first-order lag, opening tau 0.10 s (muscle), closing tau 0.55 s (elastic sac).
* states  idle, thinking, tool, review, needs-you, fault, unknown (+ degraded = unknown, no hue).
"""
from __future__ import annotations

import functools
import hashlib
import math

# ---------------------------------------------------------------- tokens (mirrored in tokens.json)

E_STEPS = 10                       # perceptual steps of expansion; finer changes are never drawn
GLYPHS = " ·•●"
GLYPH_E = (0.12, 0.42, 0.72)       # e below the first -> ' ', then '·', '•', '●'
TAU_OPEN, TAU_CLOSE = 0.10, 0.55   # seconds: muscle opens fast, elastic sac closes slow
TIER_L = (0.58, 0.66, 0.74)
TIER_C = 0.135
TIER_HUE = (-7.0, 0.0, 7.0)
TIER_CUT = (0.45, 0.80)            # cumulative: 45 % / 35 % / 20 %
TIER_TONIC = (0.26, 0.32, 0.48)    # resting expansion per tier
L_CAP = 0.86
AMBER_H, RED_H = 72.0, 27.0
GLINT = (0.90, 0.05, -25.0)        # L, C, hue offset: the pale iridophore layer at a flash peak
GREY = (0.55, 0.0)
ARC = (110.0, 340.0)
DENSITY = 0.10
BURST_EVERY = 0.25

STATES = ("idle", "thinking", "tool", "review", "needs-you", "fault", "unknown")
# Frame rate at which each state is simulated / drawn (CONTEXT-D2 motion budget). Static states
# are simulated at a low rate only so their kinetics settle; they cost 0 frames at runtime.
FPS = {"idle": 4, "thinking": 10, "tool": 10, "review": 4, "needs-you": 8, "fault": 6, "unknown": 4}

# scale -> (cols, rows, density). XL = desktop field pane, M = TUI/CLI strip, S = swatch/pill.
# S raises the density: a 4x2 swatch at 10 % would usually hold no organ at all.
SCALES = {"XL": (64, 24, DENSITY), "M": (120, 2, DENSITY), "S": (4, 2, 0.5)}


# ---------------------------------------------------------------- colour (OKLCh)

def _enc(c: float) -> int:
    c = min(1.0, max(0.0, c))
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return math.floor(c * 255 + 0.5)   # half-up: identical in JS Math.round


def _oklab_to_srgb(L: float, a: float, b: float) -> tuple[int, int, int]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        _enc(+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _enc(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _enc(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def oklch(L: float, C: float, h_deg: float) -> tuple[int, int, int]:
    h = math.radians(h_deg)
    return _oklab_to_srgb(L, C * math.cos(h), C * math.sin(h))


# ---------------------------------------------------------------- determinism


@functools.lru_cache(maxsize=1 << 16)
def h(*parts: object) -> float:
    """Deterministic uniform [0,1) from any parts (blake2b-64, never Python's hash())."""
    d = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(d, "big") / 2 ** 64


def session_hue(session: str) -> float:
    """Preview-only hue (the shipped hue comes from the 20-slot allocator): arc [110, 340)."""
    return ARC[0] + (ARC[1] - ARC[0]) * h("hue", session)


# ---------------------------------------------------------------- the organs


class Organ:
    __slots__ = ("x", "y", "tier", "phase", "rate", "alarm", "e")

    def __init__(self, x: int, y: int, tier: int, phase: float, rate: float, alarm: float):
        self.x, self.y, self.tier = x, y, tier
        self.phase, self.rate, self.alarm = phase, rate, alarm
        self.e = 0.0   # displayed expansion, 0..1 (lags the drive asymmetrically)


def constellation(seed: str, cols: int, rows: int, density: float = DENSITY) -> list[Organ]:
    """One candidate per cell kept with p=density, thinned so no two organs touch (8-neighbourhood)."""
    out: list[Organ] = []
    taken: set[tuple[int, int]] = set()
    for y in range(rows):
        for x in range(cols):
            if h("pos", seed, x, y) >= density:
                continue
            if any((x + dx, y + dy) in taken for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue
            taken.add((x, y))
            r = h("tier", seed, x, y)
            tier = 0 if r < TIER_CUT[0] else 1 if r < TIER_CUT[1] else 2
            out.append(Organ(x, y, tier, h("ph", seed, x, y), 0.7 + 0.6 * h("rt", seed, x, y),
                             h("alarm", seed, x, y)))
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
    a, b = h(seed, xi, yi), h(seed, xi + 1, yi)
    c, d = h(seed, xi, yi + 1), h(seed, xi + 1, yi + 1)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


@functools.lru_cache(maxsize=8)
def _bursts(k0: int, cols: int, rows: int) -> tuple[tuple[float, float, float, float], ...]:
    per_tick = max(1, math.floor(cols * rows / 650 + 0.5))   # same sparkle rate per area at any size
    return tuple((h("bx", k, j) * cols, h("by", k, j) * rows, 5 + 7 * h("br", k, j), k * BURST_EVERY)
                 for k in range(k0 - 4, k0 + 1) for j in range(per_tick))


def drive(o: Organ, state: str, t: float, ts: float, cols: int, rows: int,
          twinkle: bool = True) -> tuple[float, str]:
    """Target expansion 0..1 and pigment class ('id' | 'amber' | 'red' | 'glint' | 'grey').
    t = wall time, ts = time since entering the state. ``twinkle=False`` (the idle-twinkle setting
    is off) leaves idle at its tonic tone: no motion at all."""
    tonic = TIER_TONIC[o.tier]

    if state == "idle":
        # Rare individual twitches: each organ owns a slow private clock; a twitch fires when its
        # window comes up AND a seeded coin says so (18 %) -> ~1 organ / 1.5 s on a strip.
        period = 9.0 / o.rate
        k = math.floor((t + o.phase * period) / period)
        if twinkle and h("tw", o.x, o.y, k) < 0.18:
            start = k * period - o.phase * period + h("tws", o.x, o.y, k) * period * 0.5
            return min(1.0, tonic + 0.6 * _bump(t - start, 0.12, 0.9)), "id"
        return tonic, "id"

    if state == "thinking":
        # Coherent value-noise clouds advected left->right (~6 s per crossing), soft-thresholded.
        u = o.x / max(6.0, cols / 9.0) - t * 1.5
        v = o.y / max(2.0, rows / 3.5)
        n = 0.65 * vnoise(u, v, "c1") + 0.35 * vnoise(2.1 * u + 7, 2.1 * v, "c2")
        cloud = min(1.0, max(0.0, (n - 0.48) / 0.22))
        cloud = cloud * cloud * (3 - 2 * cloud)
        return 0.24 + 0.72 * cloud, "id"

    if state == "tool":
        # Sparkle bursts every 0.25 s; organs near a focus flash open in order of distance (a
        # ripple, 0.035 s per cell), then relax. The peak shows the iridophore glint.
        level = 0.25
        for cx, cy, radius, start in _bursts(math.floor(t / BURST_EVERY), cols, rows):
            dx = (o.x - cx) / 2.0   # cells are ~2:1 tall
            if abs(dx) > radius:
                continue
            dy = o.y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > radius:
                continue
            onset = start + dist * 0.035
            level = max(level, 0.95 * math.sqrt(1 - dist / radius) * _bump(t - onset, 0.08, 0.45))
        return min(1.0, level), ("glint" if level > 0.70 else "id")

    if state == "review":
        # A soft static mottle: vnoise blotches, organs hold e in 0.2..0.7 by blotch. No motion.
        n = vnoise(o.x / max(4.0, cols / 16.0), o.y / max(2.0, rows / 6.0), "rv")
        return 0.2 + 0.5 * min(1.0, max(0.0, (n - 0.2) / 0.6)), "id"

    if state == "needs-you":
        # Identity organs settle at 0.26; seeded organs (alarm<0.06) go amber and pulse in sync
        # at 0.5 Hz -- synchronous = "this is a signal, not activity".
        if o.alarm < 0.06:
            pulse = 0.5 * (1 + math.sin(2 * math.pi * 0.5 * t))
            return 0.55 + 0.45 * pulse, "amber"
        return 0.26, "id"

    if state == "fault":
        # Blanch (everything closes via the kinetics); after 0.6 s the alarm<0.10 organs flush red
        # and hold. Static.
        if o.alarm < 0.10 and ts > 0.6:
            return 0.8, "red"
        return 0.0, "id"

    if state in ("unknown", "degraded"):
        # No identity claim: sparse grey organs, static.
        return 0.5, "grey"

    raise ValueError(state)


# ---------------------------------------------------------------- appearance


@functools.lru_cache(maxsize=4096)
def _paint(tier: int, q: int, pigment: str, hue: float | None) -> tuple[str, tuple[int, int, int] | None]:
    return _appearance(tier, q / E_STEPS, pigment, hue)


def appearance(o: Organ, e: float, pigment: str, hue: float | None) -> tuple[str, tuple[int, int, int] | None]:
    """Quantised + memoised: an organ costs a terminal write only when it visibly changes."""
    return _paint(o.tier, math.floor(e * E_STEPS + 0.5), pigment, hue)


def _appearance(tier: int, e: float, pigment: str, hue: float | None) -> tuple[str, tuple[int, int, int] | None]:
    if e < GLYPH_E[0]:
        return " ", None
    g = GLYPHS[1 if e < GLYPH_E[1] else 2 if e < GLYPH_E[2] else 3]
    if pigment == "grey" or hue is None:
        return g, oklch(GREY[0], GREY[1], 0.0)
    if pigment == "amber":
        return g, oklch(0.84 * (0.80 + 0.20 * e), 0.165, AMBER_H)
    if pigment == "red":
        return g, oklch(0.71 * (0.82 + 0.18 * e), 0.215, RED_H)
    if pigment == "glint":
        return g, oklch(GLINT[0], GLINT[1], hue + GLINT[2])
    L = TIER_L[tier] * (0.80 + 0.28 * e)
    return g, oklch(min(L_CAP, L), TIER_C * (0.45 + 0.75 * e), hue + TIER_HUE[tier])


def step_kinetics(o: Organ, target: float, dt: float) -> None:
    tau = TAU_OPEN if target > o.e else TAU_CLOSE
    o.e += (target - o.e) * (1 - math.exp(-dt / tau))


# ---------------------------------------------------------------- scenes (what the vectors pin)


def render(seed: str, hue: float | None, state: str, cols: int, rows: int, entered: float,
           times: list[float], density: float = DENSITY, twinkle: bool = True) -> list[list[tuple]]:
    """Cells at each wall time in ``times`` (ascending, each >= ``entered``) for a session that
    entered ``state`` at ``entered`` with every organ closed. Fixed-step simulation at FPS[state]
    (the oracle PNG path). One snapshot per time: [(x, y, glyph, (r,g,b), pigment), ...] for the
    VISIBLE organs only (glyph != ' '), in constellation order.

    ``state`` may be 'degraded' (== unknown with no hue)."""
    if state == "degraded":
        hue = None
    sim = "unknown" if state == "degraded" else state
    if sim not in FPS:
        raise ValueError(state)
    fps = FPS[sim]
    organs = constellation(seed, cols, rows, density)
    want = [math.floor((t - entered) * fps) for t in times]
    out: list[list[tuple]] = []
    i = 0
    for n in want:
        while i <= n:
            for o in organs:
                target, _ = drive(o, sim, entered + i / fps, i / fps, cols, rows, twinkle)
                step_kinetics(o, target, 1 / fps)
            i += 1
        cells = []
        for o in organs:
            _, pig = drive(o, sim, entered + n / fps, n / fps, cols, rows, twinkle)
            g, rgb = appearance(o, o.e, pig, hue)
            if rgb is not None:
                cells.append((o.x, o.y, g, rgb, pig))
        out.append(cells)
    return out
