"""The theme must survive a terminal that cannot render 24-bit colour.

WHY THIS CONTRACT EXISTS

The goal is "I will ssh ... and type hermes". A plain ssh login forwards TERM
and usually NOT COLORTERM, and Hermes deliberately refuses to assume truecolor
from `xterm-256color` alone (agent/pet/render.py: a wrong True prints garbage).
prompt_toolkit then negotiates 8-bit and quantises every hex the theme emits
onto the 256-colour cube.

Measured on this box before this contract existed, `hermes` over a COLORTERM-less
login painted 777 indexed background escapes, 0 truecolor, and the field's
ground #0b0c10 quantised to cube index 232 = rgb(8,8,8) while the terminal
window stayed at rgb(11,12,16). A ground that merely APPROXIMATES the window is
the exact failure `_snap_to_window` exists to prevent: it reads as a panel laid
over the terminal, with a visible edge wherever painting stops.

So the theme may not be colour-depth blind. It must know the depth it is
painting for and choose colours that survive it.

These outcomes are about the 8-bit path only. The 24-bit path is already proven
by tests/test_v19_acceptance.py and tools/prove_terminal_paints.py.
"""

from __future__ import annotations

import pytest

depth = pytest.importorskip("cuttlefish_theme.v19.depth")


CUBE_GROUND_MISMATCH = "the 256-cube has no exact #0b0c10; the theme must adapt, not hope"

# xterm's 6x6x6 cube is a fixed table, not a formula. Six pigments spanning the
# hue circle, used to prove quantisation neither hides them nor merges them.
CUBE_LEVELS = (0, 95, 135, 175, 215, 255)
GREY_RAMP_BASE, GREY_RAMP_STEP, GREY_RAMP_START = 8, 10, 232
PIGMENTS = ((0x8A, 0x6F, 0x21), (0x2E, 0x5D, 0x8A), (0xC2, 0xC2, 0x57),
            (0x6F, 0x52, 0x01), (0x1E, 0x09, 0x41), (0xA0, 0x40, 0x70))


def _cube_rgb(index: int) -> tuple[int, int, int]:
    """The sRGB an xterm-256 index actually paints."""
    if index >= GREY_RAMP_START:
        value = GREY_RAMP_BASE + (index - GREY_RAMP_START) * GREY_RAMP_STEP
        return (value, value, value)
    offset = index - 16
    return (CUBE_LEVELS[offset // 36], CUBE_LEVELS[(offset % 36) // 6], CUBE_LEVELS[offset % 6])


class TestDepthIsKnown:
    """Outcome 1-3: the theme can state the depth it is painting for."""

    def test_the_module_reports_a_depth(self):
        assert depth.current_depth() in (depth.Depth.TRUECOLOR, depth.Depth.INDEXED_256)

    def test_colorterm_truecolor_means_truecolor(self, monkeypatch):
        monkeypatch.setenv("COLORTERM", "truecolor")
        assert depth.current_depth() is depth.Depth.TRUECOLOR

    def test_a_bare_256_colour_login_is_NOT_truecolor(self, monkeypatch):
        """This is the ssh case the whole contract exists for."""
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        assert depth.current_depth() is depth.Depth.INDEXED_256


class TestGroundSurvivesQuantisation:
    """Outcome 4-6: the unlit ground must still equal the window colour."""

    def test_the_indexed_ground_is_an_exact_cube_entry(self):
        """A ground that round-trips through the cube unchanged has no edge."""
        ground = depth.ground_for(depth.Depth.INDEXED_256)
        index = depth.nearest_cube_index(ground)
        assert _cube_rgb(index) == ground, CUBE_GROUND_MISMATCH

    def test_the_truecolor_ground_is_unchanged(self):
        """The 24-bit path must keep the colour the window already uses."""
        assert depth.ground_for(depth.Depth.TRUECOLOR) == (0x0B, 0x0C, 0x10)

    def test_the_two_grounds_are_close_enough_to_be_the_same_skin(self):
        """Switching terminals may shift the ground, but not the identity."""
        true_ground = depth.ground_for(depth.Depth.TRUECOLOR)
        cube_ground = depth.ground_for(depth.Depth.INDEXED_256)
        assert sum(abs(a - b) for a, b in zip(true_ground, cube_ground)) <= 24


class TestPigmentSurvivesQuantisation:
    """Outcome 7-9: sparse pigment must stay visible and varied at 8-bit."""

    def test_pigment_does_not_collapse_onto_the_ground(self):
        """Quantisation must not turn lit cells back into unlit ones."""
        ground_index = depth.nearest_cube_index(depth.ground_for(depth.Depth.INDEXED_256))
        collapsed = [c for c in PIGMENTS if depth.nearest_cube_index(c) == ground_index]
        assert not collapsed, f"{len(collapsed)} lit colours quantised onto the ground"

    def test_distinct_pigments_stay_distinct(self):
        """Six clearly different pigments must not become one cube entry."""
        assert len({depth.nearest_cube_index(c) for c in PIGMENTS}) >= 5

    def test_nearest_cube_index_is_in_range(self):
        for colour in ((0, 0, 0), (255, 255, 255), (11, 12, 16), (130, 90, 40)):
            assert 16 <= depth.nearest_cube_index(colour) <= 255


class TestTheRendererUsesIt:
    """Outcome 10-11: the wiring, not just the helper."""

    def test_the_renderer_paints_the_depth_appropriate_ground(self, monkeypatch):
        """Under a 256-colour login the unlit cells must use the cube ground."""
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        renderer = pytest.importorskip("cuttlefish_theme.v19.renderer")
        renderer.clear_caches()
        row = renderer.transcript_row(session_id="ssh-probe", width=120, row=1,
                                      time_ms=0, occupied=False)
        expected = depth.ground_for(depth.Depth.INDEXED_256)
        assert row.count(expected) > len(row) // 2, (
            "most cells must be the cube-exact ground, or the field reads as a panel")

    def test_truecolor_rendering_is_unchanged(self, monkeypatch):
        """The fix must not alter what a truecolor terminal already gets."""
        monkeypatch.setenv("COLORTERM", "truecolor")
        renderer = pytest.importorskip("cuttlefish_theme.v19.renderer")
        renderer.clear_caches()
        row = renderer.transcript_row(session_id="ssh-probe", width=120, row=1,
                                      time_ms=0, occupied=False)
        assert row.count((0x0B, 0x0C, 0x10)) > len(row) // 2
