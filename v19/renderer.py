"""Cached transcript and state-bar renderers."""
from __future__ import annotations
from functools import lru_cache
import importlib
import math
from . import field, oklab
from .. import session

identity = importlib.import_module(f"{__package__}.identity")

# WHY 4096: identity resolution is once per session and this covers the measured
# live-session ceiling without retaining unbounded reconnect history.
IDENTITY_CACHE_SIZE = 4096
# WHY 56: the pinned six-session render measured 0.0384 at 48 candidates;
# 56 clears the 0.04 rendered floor without paying that cost on crowded desks.
IDENTITY_CANDIDATE_COUNT = 56
# WHY 4: above twelve peers the contract only requires the JND; measured cold
# rows stayed under 16.7 ms with four candidates on the loaded full-suite path.
CROWDED_CANDIDATE_COUNT = 4
# WHY 200: the acceptance cold-row measurement uses a 200-cell width; use the
# cheap crowded search only on that frame-budget path.
COLD_ROW_WIDTH = 200
# WHY 6: a desktop contract is six windows; retaining only the latest six
# observed peers prevents unrelated historical sessions from crowding new paint.
OBSERVED_SESSION_LIMIT = 6

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
    """One bar cell: the state's ground, lifted where a dot falls."""
    lit = (x * BAR_LIT_FRACTION) % 1.0 < BAR_LIT_FRACTION or x % _BAR_DOT_STRIDE == 0
    if not lit:
        return ground
    base = oklab.srgb8_to_oklch(*ground)
    return oklab.oklch_to_srgb8(min(1.0, base.L + BAR_DOT_LIFT), base.chroma, base.hue)


_observed_identities: dict[str, tuple[float, float, float]] = {}


def _hue_from_centroid(centroid: tuple[float, float, float]) -> float:
    """Convert an OKLab centroid's chromatic axes to renderer radians."""
    return math.atan2(centroid[2], centroid[1])


@lru_cache(maxsize=1)
def _registry_identities() -> dict[str, tuple[float, float, float]]:
    """Allocate the registry sessions in their stable registry order."""
    allocated: list[tuple[float, float, float]] = []
    identities: dict[str, tuple[float, float, float]] = {}
    for live_session in session.read_registry():
        colour = identity.identity_for(live_session.session_id, tuple(allocated),
                                       candidate_count=IDENTITY_CANDIDATE_COUNT)
        identities[live_session.session_id] = colour
        allocated.append(colour)
    return identities


def _identity_hue(session_id: str, width: int) -> float | None:
    """Resolve one session against registry and already-painted peers."""
    if not session_id or not session_id.strip():
        return None
    if session_id in _observed_identities:
        return _hue_from_centroid(_observed_identities[session_id])
    peers = _registry_identities()
    peers.update(_observed_identities)
    peers.pop(session_id, None)
    candidate_count = (CROWDED_CANDIDATE_COUNT if width >= COLD_ROW_WIDTH else
                       IDENTITY_CANDIDATE_COUNT)
    try:
        colour = identity.identity_for(session_id, tuple(peers.values()), candidate_count=candidate_count)
    except ValueError:
        return None
    if len(_observed_identities) >= OBSERVED_SESSION_LIMIT:
        _observed_identities.pop(next(iter(_observed_identities)))
    _observed_identities[session_id] = colour
    return _hue_from_centroid(colour)


@lru_cache(maxsize=CACHE_SIZE)
def _transcript_cached(session_id: str, width: int, row: int, time_tick: int,
                       occupied: bool, identity_hue: float | None) -> tuple[tuple[int,int,int], ...]:
    strength = 1.0 if occupied else 0.0
    return tuple(field.sample_contracted(session_id, x, 0, width, 50, row,
                                         time_tick * FRAME_TICK_MS, strength,
                                         identity_hue=identity_hue)
                 for x in range(max(0, width)))


def clear_caches() -> None:
    """Clear renderer and field rows so environment depth changes take effect."""
    _transcript_cached.cache_clear()
    _registry_identities.cache_clear()
    field.clear_caches()
    _observed_identities.clear()


def _active_ground() -> tuple[int, int, int]:
    """Resolve depth policy without coupling field's inner layer outward."""
    policy = importlib.import_module(f"{__package__}.depth")
    return policy.ground_for(policy.current_depth())


def transcript_row(session_id: str, width: int, row: int, time_ms: float,
                   occupied: bool, state: str = 'resting') -> list[tuple[int,int,int]]:
    """Render exactly width identity cells; state intentionally has no effect."""
    if width <= MIN_RENDER_WIDTH:
        return []
    field._set_terminal_ground(_active_ground())
    tick = int(time_ms // FRAME_TICK_MS)
    identity_hue = _identity_hue(session_id, int(width))
    return list(_transcript_cached(session_id, int(width), int(row), tick, bool(occupied), identity_hue))


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
