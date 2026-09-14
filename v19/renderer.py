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

def status_bar(session_id: str, width: int, state: str) -> list[tuple[int,int,int]]:
    """Render a session-invariant state bar."""
    del session_id
    bg, _ = _BAR[_normal_state(state)]
    oklab.srgb8_to_oklch(*bg)
    return [bg for _ in range(max(0, width))]

def status_bar_foreground(state: str) -> tuple[int,int,int]:
    """Return readable foreground colour for a state bar."""
    return _BAR[_normal_state(state)][1]
