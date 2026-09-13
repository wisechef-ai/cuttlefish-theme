"""Measured contract for the flat, dotted input rule."""
from __future__ import annotations

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import _index_to_hex, quantize_cube_256
from cuttlefish_theme.linework import cells

SIGNALS = ("resting", "needs-me", "fault")
WIDTH = 100


def rendered(hex_colour: str) -> str:
    return _index_to_hex(quantize_cube_256(hex_colour))


def test_ground_is_one_flat_colour_per_session() -> None:
    for signal in SIGNALS:
        for n in range(200):
            row = cells(f"s{n}", signal, WIDTH)
            unlit = [bg for fg, bg, _ in row if fg == bg]
            assert unlit and len(set(unlit)) == 1


def test_dots_are_sparse() -> None:
    fractions = []
    for n in range(200):
        row = cells(f"s{n}", "resting", WIDTH)
        fractions.append(sum(fg != bg for fg, bg, _ in row) / WIDTH)
    assert min(fractions) >= 0.10
    assert max(fractions) <= 0.20


def test_dots_use_the_ground_as_their_background() -> None:
    for signal in SIGNALS:
        for n in range(200):
            row = cells(f"s{n}", signal, WIDTH)
            ground = row[0][1]
            assert all(bg == ground for _fg, bg, _ in row)


def test_quantised_ground_is_mid_dark() -> None:
    for signal in SIGNALS:
        for n in range(200):
            ground = rendered(cells(f"s{n}", signal, WIDTH)[0][1])
            assert 0.20 <= hex_to_oklch(ground).L <= 0.34


def test_quantised_dots_are_brighter_than_ground() -> None:
    for n in range(200):
        row = cells(f"s{n}", "resting", WIDTH)
        ground = hex_to_oklch(rendered(row[0][1])).L
        for fg, bg, _ in row:
            if fg != bg:
                assert hex_to_oklch(rendered(fg)).L - ground >= 0.12


def test_identity_capacity_does_not_collapse() -> None:
    grounds = {cells(f"s{n}", "resting", WIDTH)[0][1] for n in range(200)}
    assert len(grounds) >= 8
