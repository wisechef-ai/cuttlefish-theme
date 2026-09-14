"""Cached transcript and state-bar renderers."""
from __future__ import annotations
from functools import lru_cache
from . import field, oklab

# WHY: these bounds keep cached transcript rendering predictable.
CACHE_SIZE = 2048
FRAME_TICK_MS = 16
MIN_RENDER_WIDTH = 0
STATES = ('resting', 'attention', 'fault')
_BAR = {
    'resting': ((20, 45, 48), (232, 238, 238)),
    'attention': ((104, 62, 8), (255, 245, 220)),
    'fault': ((105, 18, 26), (255, 240, 240)),
}

def _normal_state(state: str) -> str:
    return state if state in _BAR else 'resting'


# Share of bar cells carrying a brighter dot. A one-row surface needs a much
# higher density than a 2D field — ~11-16% measured on a mantle leaves only a
# dozen lit cells across 80 columns, which the eye reads as emptiness rather
# than as texture — but past roughly a third the dots stop reading as marks ON
# a ground and start reading as a second stripe. Measured: 0.30 with the prime
# stride lands at 44% of cells lit, which is that failure; 0.18 lands near 28%.
BAR_LIT_FRACTION = 0.18

# Lightness added to a lit cell, in OKLab L. Large enough to see, small enough
# that the bar's own foreground still clears WCAG AA against the brightest cell
# — the alarm must stay legible at its loudest, which is exactly when it speaks.
BAR_DOT_LIFT = 0.06

# Cell spacing of the dot pattern. A prime stride keeps the dots from lining up
# with the bar's own segment boundaries, which would read as banding.
_BAR_DOT_STRIDE = 7


def _bar_cell(ground: tuple[int, int, int], x: int) -> tuple[int, int, int]:
    """One bar cell: the state's ground, lifted where a dot falls.

    Only LIGHTNESS moves. Hue and chroma are the state's identity — an amber
    warning whose dots drifted toward red would blur the one distinction the
    two alarms exist to make.
    """
    lit = (x * BAR_LIT_FRACTION) % 1.0 < BAR_LIT_FRACTION or x % _BAR_DOT_STRIDE == 0
    if not lit:
        return ground
    base = oklab.srgb8_to_oklch(*ground)
    return oklab.oklch_to_srgb8(min(1.0, base.L + BAR_DOT_LIFT), base.chroma, base.hue)

@lru_cache(maxsize=CACHE_SIZE)
def _transcript_cached(session_id: str, width: int, row: int, time_tick: int,
                       occupied: bool) -> tuple[tuple[int,int,int], ...]:
    strength = 1.0 if occupied else 0.0
    return tuple(field.sample_contracted(session_id, x, 0, width, 50, row,
                                         time_tick * FRAME_TICK_MS, strength)
                 for x in range(max(0, width)))

def transcript_row(session_id: str, width: int, row: int, time_ms: float,
                   occupied: bool, state: str = 'resting') -> list[tuple[int,int,int]]:
    """Render exactly width identity cells; state intentionally has no effect."""
    if width <= MIN_RENDER_WIDTH:
        return []
    tick = int(time_ms // FRAME_TICK_MS)
    return list(_transcript_cached(session_id, int(width), int(row), tick, bool(occupied)))

def status_bar(session_id: str, width: int, state: str) -> list[tuple[int, int, int]]:
    """Render the state bar: a lit ground carrying sparse brighter pigment.

    SESSION-INVARIANT BY CONTRACT. `session_id` is accepted and deliberately
    ignored — it is part of the public shape and the guarantee is easier to see
    at a call site than in a docstring. A state that looked different in each
    window would not be a signal at all.

    The dots are what distinguish this from a painted rectangle: a flat fill
    reads as chrome, a mottled one reads as the same skin the transcript wears.
    """
    del session_id
    ground, _ = _BAR[_normal_state(state)]
    return [_bar_cell(ground, x) for x in range(max(MIN_RENDER_WIDTH, width))]

def status_bar_foreground(state: str) -> tuple[int,int,int]:
    """Return readable foreground colour for a state bar."""
    return _BAR[_normal_state(state)][1]
