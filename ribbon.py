"""Truecolor combed diagonal ribbons for the transcript mantle."""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from .color.oklab import OKLCh, oklab_to_oklch, oklch_to_hex

_BODY_FOREGROUND = "#E8E6EA"
_SIGNALS = {"resting", "needs_me", "fault"}


def _seed(session_id: str) -> bytes:
    return hashlib.blake2b(session_id.encode("utf-8"), digest_size=16).digest()


def _session_params(session_id: str) -> tuple[float, float, float]:
    raw = _seed(session_id)
    n = int.from_bytes(raw[:8], "big")
    # The phase is deliberately independent from hue: equal-looking palettes
    # must still occupy different positions in the comb.
    hue = (n % 36000) / 100.0
    phase = int.from_bytes(raw[8:12], "big") / 2**32 * math.tau
    bend = (int.from_bytes(raw[12:], "big") / 2**32 - 0.5) * 0.22
    return hue, phase, bend


def _hues(session_id: str, signal: str) -> tuple[float, ...]:
    if signal == "fault":
        return (4.0, 20.0, 36.0, 52.0, 68.0)
    if signal == "needs_me":
        return (38.0, 50.0, 62.0, 74.0, 86.0)
    base, _, _ = _session_params(session_id)
    return tuple((base + i * 58.0) % 360.0 for i in range(6))


def _colour(hue: float, lightness: float) -> str:
    # Chroma is kept modest so every hue remains in gamut at the dark readable L.
    return oklch_to_hex(OKLCh(lightness, 0.075, hue))


@lru_cache(maxsize=2048)
def _row_hex(session_id: str, width: int, row: int, signal: str) -> tuple[str, ...]:
    if signal not in _SIGNALS:
        raise ValueError(f"unknown signal: {signal!r}")
    width = max(0, int(width))
    if width == 0:
        return ()
    base_hue, phase, bend = _session_params(session_id)
    if signal != "resting":
        # Alarms must be comparable across windows; identity belongs only to calm skin.
        phase, bend = 0.0, 0.0
    hues = _hues(session_id, signal)
    # Frequency rises gently to the right, making the right third visibly denser
    # without introducing a discontinuity at any cell boundary.
    result: list[str] = []
    for x in range(width):
        xf = x / max(1, width - 1)
        density = 0.075 + 0.010 * xf
        u = (row - 0.62 * x + bend * x * x / max(1, width)) * density + phase
        ribbon = math.sin(u)
        # A bright spine and dark inter-ribbon troughs, with only a small L span;
        # the narrow span is what keeps a line of text uniformly readable.
        spine = 0.5 + 0.5 * ribbon
        along = 0.006 * math.sin(x * 0.11 + row * 0.07 + phase)
        lightness = 0.205 + 0.028 * spine + along
        # Hue belongs to the ribbon lane, while a tiny continuous blend prevents
        # quantisation-like colour edges when the spine crosses a cell.
        lane = int(math.floor((u / math.tau) * len(hues))) % len(hues)
        next_lane = (lane + 1) % len(hues)
        blend = (u / math.tau * len(hues)) % 1.0
        hue = (hues[lane] * (1.0 - blend) + hues[next_lane] * blend) % 360.0
        result.append(_colour(hue, lightness))
    return tuple(result)


@lru_cache(maxsize=1024)
def ribbon_row(session_id: str, width: int, row: int, signal: str) -> tuple[tuple[str, str], ...]:
    """Return one cached prompt-toolkit row of truecolor background fragments."""
    return tuple((f"bg:{colour}", " ") for colour in _row_hex(session_id, width, row, signal))


@lru_cache(maxsize=256)
def ribbon_field(session_id: str, width: int, height: int, signal: str) -> tuple[tuple[str, ...], ...]:
    """Return the deterministic mantle as a height-by-width hex grid."""
    if signal not in _SIGNALS:
        raise ValueError(f"unknown signal: {signal!r}")
    width, height = max(0, int(width)), max(0, int(height))
    return tuple(_row_hex(session_id, width, row, signal) for row in range(height))


@lru_cache(maxsize=1024)
def bar_cells(session_id: str, width: int, signal: str) -> tuple[tuple[str, str, str], ...]:
    """Return a thin status bar using the same mantle colors as the field."""
    backgrounds = _row_hex(session_id, width, 0, signal)
    return tuple((_BODY_FOREGROUND, background, "━") for background in backgrounds)


__all__ = ["ribbon_row", "ribbon_field", "bar_cells"]
