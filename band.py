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


# The hue arcs the acute signals own, widened for the quantiser's reach. THE
# single definition: `linework` drops resting bar colours inside these, and
# `resting_families` drops any band family that falls inside one. Two copies of
# this range drifted apart once already — the bar reserved 350-360/0-50 while
# identity reserved 5-48, so a hue-49 colour was calm to one and an alarm to the
# other.
_ALARM_ARCS: tuple[tuple[float, float], ...] = ((350.0, 410.0), (55.0, 115.0))


def reserved_for_alarm(hue: float) -> bool:
    """Whether `hue` sits in an arc the acute signals own.

    Arcs may run past 360 (the red arc wraps), so the hue is tested at both
    x and x+360 rather than the arc being normalised — normalising splits one
    arc into two and the wrap-around case gets silently dropped.
    """
    x = hue % 360.0
    return any(lo <= h <= hi for lo, hi in _ALARM_ARCS for h in (x, x + 360.0))


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


@lru_cache(maxsize=1)
def resting_families() -> tuple[tuple[str, ...], ...]:
    """Families a RESTING session may take as its dominant — alarm hues excluded.

    The readable dark band holds nine colours in three hue families, and one of
    those families IS the alarm (`#5F0000`/`#870000`, hue 29, inside the arc).
    Letting a resting session take it costs twice:

    - It breaks the signal. A calm session wearing the fault hue is the defect
      PLAN-v13 recorded as the unavoidable "one shared index" (contract 9). It is
      only unavoidable while red is a resting option.
    - It breaks coherence. `linework` must displace any bar colour sitting in the
      alarm arc so a resting bar cannot impersonate an alarm, and any such
      displacement moves the bar off its own mantle's hue.

    Removing red from the resting set fixes both at the source: red belongs to
    the alarm now, and only to the alarm — which is what makes it mean something.

    The cost is honest and bounded: two dominant families instead of three, and
    islands drawn from one other family rather than two. Identity separation is
    carried by shade and island selection WITHIN a family, not by family count.
    """
    calm = tuple(group for group in families()
                 if not any(reserved_for_alarm(hex_to_oklch(c).h) for c in group))
    # Never return empty: a misconfigured band that reserved everything must
    # degrade to the full set rather than leave a session with no colour at all.
    return calm or families()
