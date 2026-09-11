"""The v13 palette: one dominant hue family, small islands, one narrow band.

Three rounds of tuning failed because *readable* and *smooth* were treated as
one problem. They are two, with different causes:

* legibility is driven by the LIGHTNESS SPREAD a line of text crosses;
* "confetti, not one skin" is driven by HUE ALLOCATION.

Adam's reframe splits them: give a session ONE dominant hue family carrying most
of the pattern, with small islands of other hues. Needing shades of a single hue
rather than four is what lets the whole palette fit inside a narrow lightness
band, and the islands supply the colour interest a monochrome ramp would lack.

The band is the binding constraint. Measured over the xterm-256 cube, chromatic
entries per OKLab lightness band:

    L 0.15-0.25 :  1        L 0.35-0.45 :  8
    L 0.25-0.35 :  4        L 0.45-0.55 : 20

so a dark narrow band holds almost nothing, and a band wide enough to hold a
palette destroys legibility. `dither` resolves that by manufacturing perceived
tones between real ones; this module's job is only to choose real anchors that
sit inside the band.
"""
from __future__ import annotations

from functools import lru_cache

from .color.oklab import hex_to_oklch
from .color.terminal import _index_to_hex, contrast_ratio

# The band every mantle colour lives in. Measured trade-off (tools/measure_band.py,
# which sweeps this pair and reports palette cost): centre .35 width .14 drops the
# ground floor to L .282 — darker than the .36/.12 it replaces, whose floor was
# .305 — while HOLDING 9 chromatic cube entries across 3 hue families, so identity
# improves rather than degrades (86 distinct palettes per 120 sessions, against 79).
# Adam, 2026-09-11: "the background colour is too bright, it should be a little
# more tinted, little more toward black."
#
# Going darker by lowering the CENTRE instead is the trap: .32/.12 reaches the same
# floor but collapses the band to 5 colours and 10 palettes per 120 sessions, with
# 22 sessions sharing one — the mantle stops carrying identity, which is its job.
# Widening around a slightly lower centre buys the dark floor without that cost.
_BAND_CENTRE = 0.35
_BAND_WIDTH = 0.14

# A background is not text: WCAG's large-object threshold is the right bar.
_BODY_FOREGROUND = "#E8E6EA"
_MIN_CONTRAST = 3.0

# Below this a colour reads as grey and carries no family.
_MIN_CHROMA = 0.02

# Hue families are 60-degree buckets: wide enough that two shades of "blue" land
# together, narrow enough that blue and violet stay distinct.
_FAMILY_ARC = 60.0


@lru_cache(maxsize=1)
def band() -> tuple[str, ...]:
    """Every cube colour inside the readable band, darkest first.

    Cached because it is a constant of the terminal, not of the session.
    """
    inside = []
    floor = _BAND_CENTRE - _BAND_WIDTH / 2
    ceiling = _BAND_CENTRE + _BAND_WIDTH / 2
    for index in range(16, 232):
        colour = _index_to_hex(index)
        oklch = hex_to_oklch(colour)
        if not floor <= oklch.L <= ceiling or oklch.C <= _MIN_CHROMA:
            continue
        if contrast_ratio(_BODY_FOREGROUND, colour) >= _MIN_CONTRAST:
            inside.append(colour)
    return tuple(sorted(inside, key=lambda hex_colour: hex_to_oklch(hex_colour).L))


def family_of(colour: str) -> int:
    """The hue bucket `colour` belongs to, as a multiple of _FAMILY_ARC."""
    return int(hex_to_oklch(colour).h // _FAMILY_ARC)


@lru_cache(maxsize=1)
def families() -> tuple[tuple[str, ...], ...]:
    """The band's colours grouped by hue family, largest family first.

    A session picks one of these as its dominant; the rest supply islands.
    """
    grouped: dict[int, list[str]] = {}
    for colour in band():
        grouped.setdefault(family_of(colour), []).append(colour)
    return tuple(sorted((tuple(members) for members in grouped.values()),
                        key=len, reverse=True))
