"""The spacing must reach the pixels, not just the module.

WHY THIS CONTRACT EXISTS

tests/test_v19_identity_spacing.py passed 9/9 against v19/identity.py while the
live renderer was bit-for-bit unchanged, because NOTHING IMPORTED THE MODULE.
Measured at that moment, twelve random six-window desktops rendered through
renderer.transcript_row gave worst-pair OKLab separations of:

    0.004 0.023 0.024 0.037 0.048 0.050 0.052 0.055 0.059 0.061 0.083 0.086

— identical to the pre-fix numbers, while identity.py in isolation produced
0.1609 at worst. A correct module that no caller reaches is not a fix.

So this contract asserts the property on the SURFACE THE USER SEES: the colours
that come out of the renderer, not the colours the allocator could produce.

It deliberately does not pin a specific colour to a specific session. It pins
the only thing the user can act on: two windows open at once must not wear the
same face.
"""

from __future__ import annotations

import math
from itertools import combinations

import pytest

renderer = pytest.importorskip("cuttlefish_theme.v19.renderer")
oklab = pytest.importorskip("cuttlefish_theme.v19.oklab")
depth = pytest.importorskip("cuttlefish_theme.v19.depth")

# The unlit ground; excluded so a centroid describes the PIGMENT, not the
# terminal background every session shares by design. Depth-aware: an indexed
# (8-bit) session paints ground #080808 — the nearest xterm-256 entry — so
# pinning the truecolor hex there counts every unlit cell as pigment and the
# separation metric collapses on a healthy renderer.
GROUND = depth.ground_for(depth.current_depth())

# A just-noticeable difference in OKLab is ~0.02. The renderer must clear it
# with margin: measured, an unwired renderer produced 0.0035 at worst.
MIN_RENDERED_SEPARATION = 0.04

DESKTOP_SIZE = 6
SAMPLE_ROWS = 3
SAMPLE_WIDTH = 120

Centroid = tuple[float, float, float]


def _as_oklab(cell: tuple[int, int, int]) -> Centroid:
    """One painted cell as OKLab. Hue is RADIANS, so a/b are its components."""
    colour = oklab.srgb8_to_oklch(*cell)
    return (colour.L,
            colour.chroma * math.cos(colour.hue),
            colour.chroma * math.sin(colour.hue))


def _rendered_centroid(session_id: str) -> Centroid:
    """The mean OKLab of the pigment this session actually paints."""
    lit = [
        _as_oklab(cell)
        for row in range(SAMPLE_ROWS)
        for cell in renderer.transcript_row(
            session_id=session_id, width=SAMPLE_WIDTH, row=row, time_ms=0, occupied=False
        )
        if cell != GROUND
    ]
    assert lit, f"{session_id} painted no pigment at all"
    return tuple(sum(axis) / len(lit) for axis in zip(*lit))  # type: ignore[return-value]


def _worst_rendered_separation(session_ids: list[str]) -> float:
    """Closest pair among the colours these sessions actually render."""
    centroids = [_rendered_centroid(session_id) for session_id in session_ids]
    return min(math.dist(a, b) for a, b in combinations(centroids, 2))


class TestTheUserCanTellWindowsApart:
    """The README's promise, asserted on rendered output."""

    def test_six_rendered_sessions_are_distinguishable(self):
        worst = _worst_rendered_separation([f"render-{n}" for n in range(DESKTOP_SIZE)])
        assert worst >= MIN_RENDERED_SEPARATION, (
            f"two windows render only {worst:.4f} apart — the user cannot tell them apart")

    def test_an_awkward_id_set_is_still_distinguishable(self):
        """A desktop MEASURED to collide before the fix.

        These six ids are not arbitrary: sampling twelve random six-window
        desktops against the unwired renderer, this one produced the worst pair
        in the whole sample at 0.0035 — a quarter of a just-noticeable
        difference, i.e. two windows a human reads as identical. Pinning the
        real counter-example keeps this contract honest; a set of convenient
        ids passes on broken code and proves nothing.
        """
        ids = ["sess-85826", "sess-36459", "sess-53317",
               "sess-72255", "sess-10905", "sess-92774"]
        worst = _worst_rendered_separation(ids)
        assert worst >= MIN_RENDERED_SEPARATION, f"only {worst:.4f} apart"

    def test_rendering_is_stable_for_one_session(self):
        """Spacing must not make a session's own face flicker between calls."""
        first = _rendered_centroid("steady")
        second = _rendered_centroid("steady")
        assert math.dist(first, second) == 0.0
