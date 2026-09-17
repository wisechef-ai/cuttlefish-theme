"""Truecolor combed diagonal ribbons for the transcript mantle."""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from .color.oklab import OKLCh, oklab_to_oklch, oklch_to_hex

_BODY_FOREGROUND = "#E8E6EA"
# The bar carries WHITE text (Adam: "the bars should be bright and the text is
# white"), which pins the band from both ends: bright enough to read as a lit
# strip (L >= 0.50) yet dark enough to hold white at AA. Measured across the
# whole hue wheel, L .505-.55 at C .115 is the window that satisfies both
# (worst case 4.57:1); at L .56 white falls to 4.39:1 and at .50 the bar stops
# being bright. Truecolor only — no (L, C) band survives xterm-256
# quantisation with both properties intact, which is why this path needs the
# 24-bit negotiation.
_BAR_L = (0.505, 0.55)
_BAR_FOREGROUND = "#FFFFFF"
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
    """The ribbon lanes — ALWAYS the session's own, in every state.

    Adam, 2026-09-12: "per session no big background changes ... the background
    change makes the recognition of terminal harder".

    The background is the IDENTITY channel and nothing else. An earlier cut
    repainted the whole field amber on `needs_me` and red on `fault`, which
    meant the one surface you use to recognise a window changed the moment that
    window had something to say — you lost the terminal exactly when you needed
    to find it. State is carried by `bar_cells`, which replaces the pet's
    information role; the field stays still underneath it.
    """
    base, _, _ = _session_params(session_id)
    return tuple((base + i * 58.0) % 360.0 for i in range(6))


# Acute bar lanes: fixed, ascending, NON-OVERLAPPING, and identical in every
# window so "that one needs me" reads the same across six terminals. Fault owns
# red (<=42), needs_me owns amber (>=60), an 18-degree gap. A first cut spanned
# 4-68 and 38-86, so the two alarms shared 38-68 and "failed" was unreadable
# against "waiting" — an alarm you cannot tell from the other alarm is not a
# signal. Both stay clear of the 0/360 seam, which the lane blend would
# otherwise cross the long way round.
_ACUTE_HUES = {
    "fault": (2.0, 12.0, 22.0, 32.0, 42.0),
    "needs_me": (60.0, 72.0, 84.0, 96.0, 108.0),
}


def _colour(hue: float, lightness: float) -> str:
    # Chroma is kept modest so every hue remains in gamut at the dark readable L.
    return oklch_to_hex(OKLCh(lightness, 0.075, hue))


@lru_cache(maxsize=2048)
def _row_hex(session_id: str, width: int, row: int, signal: str) -> tuple[str, ...]:
    """One row of the mantle. `signal` is accepted and deliberately unused.

    Kept in the signature because it is part of the cache key and the public
    surface: callers pass the live signal, and the contract they are relying on
    is that the answer does NOT change with it. Dropping the parameter would
    make that guarantee invisible at the call site.
    """
    if signal not in _SIGNALS:
        raise ValueError(f"unknown signal: {signal!r}")
    width = max(0, int(width))
    if width == 0:
        return ()
    _, phase, bend = _session_params(session_id)
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
    """A thin bar: the session's own colours at rest, the shared alarm when acute.

    THIS is the state channel — it replaces what the pet used to tell you, and
    it is the only surface that moves. At rest it wears the session's ribbon
    hues so the bar belongs to its window; on `needs_me`/`fault` it takes the
    fixed amber/red lanes, identical everywhere, so one glance across six
    terminals answers "which one needs me" without decoding anything.

    Kept thin and multi-toned rather than one flat block (Adam, 2026-09-12:
    "thin bar but with multiple colors not like a rainbow"): the lanes are
    neighbours in hue, so it reads as one lit strip with structure, not tinsel.
    """
    width = max(0, int(width))
    if width == 0:
        return ()
    hues = _ACUTE_HUES.get(signal) or _hues(session_id, signal)
    phase = 0.0 if signal in _ACUTE_HUES else _session_params(session_id)[1]
    floor, ceiling = _BAR_L
    cells = []
    for x in range(width):
        u = x * 0.16 + phase
        lane = int((u / math.tau) * len(hues)) % len(hues)
        lightness = floor + (ceiling - floor) * (0.5 + 0.5 * math.sin(u))
        cells.append((_BAR_FOREGROUND, oklch_to_hex(OKLCh(lightness, 0.115, hues[lane])), "━"))
    return tuple(cells)


__all__ = ["ribbon_row", "ribbon_field", "bar_cells"]
