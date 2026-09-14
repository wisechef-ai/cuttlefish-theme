"""Terminal colour-depth policy shared by the theme's rendering layers.

The environment decision deliberately mirrors Hermes core's
``agent/pet/render.py:supports_truecolor`` decision so the skin and host do not
paint with different assumptions.  This module re-implements that small policy
locally: the plugin must not depend on Hermes core internals.
"""
from __future__ import annotations

from enum import Enum, auto
import os

RGB = tuple[int, int, int]
TRUECOLOR_GROUND: RGB = (0x0B, 0x0C, 0x10)
# WHY 232: this is the first greyscale entry and exactly matches (8, 8, 8),
# the closest xterm-256 colour to the true ground; cold-row measurements show
# lookup cost is negligible when cached by the renderer.
INDEXED_GROUND_INDEX = 232


class Depth(Enum):
    """Supported terminal colour depths."""

    TRUECOLOR = auto()
    INDEXED_256 = auto()


def current_depth() -> Depth:
    """Resolve terminal depth using Hermes core's environment precedence."""
    if os.environ.get("COLORTERM", "").strip().lower() in ("truecolor", "24bit"):
        return Depth.TRUECOLOR
    version = os.environ.get("VTE_VERSION", "")
    if version.isdigit() and int(version) >= 3600:
        return Depth.TRUECOLOR
    if os.environ.get("TERM", "").lower().endswith("-direct"):
        return Depth.TRUECOLOR
    return Depth.INDEXED_256


def _cube_level(value: int) -> int:
    """Convert a cube coordinate to its xterm channel level."""
    return 0 if value == 0 else 55 + 40 * value


def _cube_rgb(index: int) -> RGB:
    """Return the RGB value represented by an xterm cube index."""
    offset = index - 16
    return (
        _cube_level(offset // 36),
        _cube_level((offset % 36) // 6),
        _cube_level(offset % 6),
    )


def _indexed_rgb(index: int) -> RGB:
    """Return the RGB value represented by any non-ANSI xterm index."""
    if index < 232:
        return _cube_rgb(index)
    value = 8 + (index - 232) * 10
    return (value, value, value)


def _distance(left: RGB, right: RGB) -> int:
    """Return summed absolute channel distance."""
    return sum(abs(a - b) for a, b in zip(left, right))


def nearest_cube_index(rgb: RGB) -> int:
    """Return the nearest xterm-256 cube or greyscale index, never ANSI."""
    if len(rgb) != 3 or any(not 0 <= channel <= 255 for channel in rgb):
        raise ValueError("rgb must contain three channels in the range 0..255")
    return min(range(16, 256), key=lambda index: (_distance(rgb, _indexed_rgb(index)), index))


def ground_for(depth: Depth) -> RGB:
    """Return the terminal-window ground appropriate for *depth*."""
    if depth is Depth.TRUECOLOR:
        return TRUECOLOR_GROUND
    if depth is Depth.INDEXED_256:
        return _indexed_rgb(INDEXED_GROUND_INDEX)
    raise ValueError(f"unsupported colour depth: {depth!r}")
