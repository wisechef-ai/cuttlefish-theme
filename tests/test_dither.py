from __future__ import annotations

from itertools import pairwise

from prompt_toolkit.styles import Style
from wcwidth import wcswidth

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import quantize_cube_256
from cuttlefish_theme.dither import blend, perceived, ramp, tone_count


IN_BAND = ("#000087", "#5F0000", "#5F005F", "#0000AF")


def _glyph_fraction(glyph: str) -> float:
    return {" ": 0.0, "▗": 0.25, "▐": 0.5, "▛": 0.75, "█": 1.0}[glyph]


def _blend_lightness(fragment: tuple[str, str]) -> float:
    style, glyph = fragment
    fields = dict(part.split(":", 1) for part in style.split())
    lower = fields["bg"]
    upper = fields.get("fg", lower)
    return hex_to_oklch(perceived(lower, upper, _glyph_fraction(glyph))).L


def test_in_band_cube_colours_multiply_into_distinct_tones() -> None:
    assert tone_count(IN_BAND) >= 12


def test_perceived_lightness_is_monotonic_and_between_anchors() -> None:
    lower, upper = IN_BAND[:2]
    values = [hex_to_oklch(perceived(lower, upper, fraction)).L for fraction in (0, .25, .5, .75, 1)]
    assert all(a <= b for a, b in pairwise(values))
    assert values[0] <= values[2] <= values[-1]


def test_blend_is_a_valid_prompt_toolkit_fragment() -> None:
    for fraction in (0, .25, .5, .75, 1):
        style, glyph = blend(IN_BAND[0], IN_BAND[1], fraction)
        Style.from_dict({"dither": style})
        assert wcswidth(glyph) == 1
        if fraction in (0, 1):
            assert glyph == " "


def test_quadrant_glyphs_stay_in_block_elements() -> None:
    for fraction in (.25, .5, .75):
        glyph = blend(IN_BAND[0], IN_BAND[1], fraction)[1]
        assert 0x2580 <= ord(glyph) <= 0x259F


def test_ramp_is_monotonic_without_duplicate_tones() -> None:
    anchors = IN_BAND
    output = ramp(anchors, 5)
    lightness = [_blend_lightness(fragment) for fragment in output]
    assert all(a <= b for a, b in pairwise(lightness))
    assert all(b - a > 0 for a, b in pairwise(lightness))


def test_quantised_anchors_are_cube_colours() -> None:
    assert all(16 <= quantize_cube_256(colour) < 232 for colour in IN_BAND)
