"""Behavioural contracts for the truecolor mantle."""
from __future__ import annotations

import math
import re
import time

from cuttlefish_theme.color.oklab import hex_to_oklch, relative_luminance
from cuttlefish_theme.ribbon import bar_cells, ribbon_field, ribbon_row

_FG = "#E8E6EA"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def contrast(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def test_public_shapes_and_truecolor_fragments():
    field = ribbon_field("shape", 31, 7, "resting")
    assert len(field) == 7 and all(len(row) == 31 for row in field)
    assert all(_HEX.fullmatch(c) for row in field for c in row)
    row = ribbon_row("shape", 31, 3, "resting")
    assert len(row) == 31
    assert all(style.startswith("bg:#") and len(style) == 10 and text == " " for style, text in row)
    assert all(len(cell) == 3 for cell in bar_cells("shape", 31, "resting"))


def test_every_surface_colour_is_wcag_aa_readable():
    for signal in ("resting", "needs_me", "fault"):
        field = ribbon_field("contrast", 100, 20, signal)
        assert min(contrast(c, _FG) for row in field for c in row) >= 4.5


def test_horizontal_oklab_lightness_is_smooth():
    field = ribbon_field("smooth", 120, 24, "resting")
    maximum = max(
        abs(hex_to_oklch(row[x]).L - hex_to_oklch(row[x - 1]).L)
        for row in field for x in range(1, len(row))
    )
    assert maximum <= 0.06


def test_each_row_has_uniform_contrast():
    field = ribbon_field("uniform", 120, 24, "resting")
    for row in field:
        ratios = [contrast(c, _FG) for c in row]
        assert max(ratios) / min(ratios) <= 1.6


def test_session_identity_and_signal_semantics():
    fields = {ribbon_field(f"s{n}", 80, 12, "resting") for n in range(200)}
    assert len(fields) >= 150
    faults = {ribbon_field(f"s{n}", 80, 12, "fault") for n in range(20)}
    needs = {ribbon_field(f"s{n}", 80, 12, "needs_me") for n in range(20)}
    assert len(faults) == 1 and len(needs) == 1
    assert next(iter(faults)) != ribbon_field("s0", 80, 12, "resting")
    assert next(iter(needs)) != ribbon_field("s0", 80, 12, "resting")
    fault_hues = {round(hex_to_oklch(c).h) for row in next(iter(faults)) for c in row}
    assert max(fault_hues) < 100 or min(fault_hues) > 300
    need_hues = {round(hex_to_oklch(c).h) for row in next(iter(needs)) for c in row}
    assert min(need_hues) >= 20 and max(need_hues) <= 110


def test_warm_row_rendering_is_cached_and_fast():
    ribbon_row("timing", 80, 4, "resting")
    start = time.perf_counter_ns()
    for _ in range(10000):
        ribbon_row("timing", 80, 4, "resting")
    micros = (time.perf_counter_ns() - start) / 10000 / 1000
    assert micros <= 15
    assert ribbon_row.cache_info().hits >= 10000
