"""Perceptual terminal-cell dithering for narrow colour ramps.

A terminal cell has one background colour, while a block glyph can expose a
second colour in part of that cell.  The helpers here keep that sub-cell mix
honest by quantising both colours before doing OKLab arithmetic.
"""

from __future__ import annotations

import math
from typing import Sequence

from .color.oklab import (
    OKLCh,
    hex_to_oklch,
    hex_to_rgb,
    oklab_to_oklch,
    oklch_to_hex,
    srgb_to_oklab,
)
from .color.terminal import _index_to_hex, quantize_cube_256

__all__ = ["blend", "perceived", "ramp", "tone_count"]


# One, two, and three filled quadrants. Orientation is deliberately immaterial
# to colour area; these are all ordinary Unicode Block Elements.
_GLYPHS = {1: "▗", 2: "▐", 3: "▛"}


def _check_fraction(fraction: float) -> None:
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0.0 and 1.0")


def _quantised(hex_colour: str) -> str:
    return _index_to_hex(quantize_cube_256(hex_colour))


def _lab(hex_colour: str) -> tuple[float, float, float]:
    return srgb_to_oklab(*hex_to_rgb(hex_colour))


def _tone_lightness(hex_colour: str) -> float:
    return hex_to_oklch(hex_colour).L


def perceived(lower_hex: str, upper_hex: str, fraction: float) -> str:
    """Return the displayed hex for an area-weighted OKLab colour mix.

    At the endpoints the anchor is returned verbatim: there is nothing to mix,
    and the OKLab round-trip is lossy enough to drift (#000087 came back as
    #001579), which breaks any caller that compares a blend against its anchor.
    """
    _check_fraction(fraction)
    lower, upper = _quantised(lower_hex), _quantised(upper_hex)
    if fraction <= 0.0:
        return lower
    if fraction >= 1.0:
        return upper
    mixed = tuple(a + (b - a) * fraction for a, b in zip(_lab(lower), _lab(upper)))
    return oklch_to_hex(oklab_to_oklch(*mixed))


def blend(lower_hex: str, upper_hex: str, fraction: float) -> tuple[str, str]:
    """Render a quarter-resolution mix as a prompt_toolkit fragment."""
    _check_fraction(fraction)
    lower, upper = _quantised(lower_hex), _quantised(upper_hex)
    filled = min(4, max(0, math.floor(fraction * 4 + 0.5)))
    if filled == 0:
        return (f"bg:{lower}", " ")
    if filled == 4:
        return (f"bg:{upper}", " ")
    return (f"fg:{upper} bg:{lower}", _GLYPHS[filled])


def ramp(colours: Sequence[str], steps: int) -> tuple[tuple[str, str], ...]:
    """Return a quarter-cell dithered ramp through dark-to-light anchors."""
    if len(colours) < 2:
        raise ValueError("ramp requires at least two anchor colours")
    if steps < 1:
        raise ValueError("steps must be positive")
    if steps == 1:
        return (blend(colours[0], colours[1], 0.0),)
    span = len(colours) - 1
    result: list[tuple[str, str]] = []
    for index in range(steps):
        position = index * span / (steps - 1)
        anchor = min(span - 1, math.floor(position))
        fraction = position - anchor
        result.append(blend(colours[anchor], colours[anchor + 1], fraction))
    return tuple(result)


def tone_count(colours: Sequence[str]) -> int:
    """Count OKLab-lightness-separated tones from all anchor-pair dithers."""
    if not colours:
        return 0
    quantised = tuple(_quantised(colour) for colour in colours)
    if len(quantised) == 1:
        return 1
    total = 0
    for left, lower in enumerate(quantised):
        for upper in quantised[left + 1:]:
            values = [_tone_lightness(lower), _tone_lightness(upper)]
            values.extend(
                _tone_lightness(perceived(lower, upper, fraction))
                for fraction in (0.25, 0.5, 0.75)
            )
            distinct = 0
            previous = -math.inf
            for value in sorted(values):
                if value - previous > 0.012:
                    distinct += 1
                    previous = value
            total += distinct
    return total
