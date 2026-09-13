"""Measured contract for the flat, dotted input rule."""
from __future__ import annotations

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import _index_to_hex, quantize_256, quantize_cube_256
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
    """Identity rides the DOTS, not the ground — so measure the dots.

    Written against the ground alone, and that was the wrong carrier. Adam,
    2026-09-13, choosing how this surface should work: "near-black ground, but
    let the dots themselves carry the per-session identity (fewer, brighter,
    session-hued)". The ground is deliberately near-uniform — it is one flat
    line, and its hue is pinned to the shared cross-surface anchor so every
    window wears one theme — so counting distinct grounds measures the thing the
    design intends to hold STILL and reports a correct implementation as a
    collapse (measured: 6 grounds, against 113 distinct dot class-sets).

    What must not collapse is what the user can actually tell apart: the set of
    dot colours a session paints. Measured on the QUANTISED values, because two
    dot-sets differing only below the cube's resolution are the same rule to the
    eye.
    """
    dot_sets = {frozenset(quantize_256(fg) for fg, bg, _ in cells(f"s{n}", "resting", WIDTH)
                          if fg != bg)
                for n in range(200)}
    assert len(dot_sets) >= 30, f"only {len(dot_sets)} distinct dot sets over 200 sessions"


def test_the_ground_is_deliberately_near_uniform() -> None:
    """The other half of the contract above, asserted so it cannot drift back.

    A future change that re-derives the ground per session would restore the
    distinct-ground count and silently break cross-surface hue coherence — the
    regression this file's own history contains (20/20 sessions sharing a hue
    family with the palette, down to 4/20). Pin the intent: few grounds, many
    dot sets.
    """
    grounds = {quantize_256(cells(f"s{n}", "resting", WIDTH)[0][1]) for n in range(200)}
    assert len(grounds) <= 12, (
        f"{len(grounds)} distinct grounds: the rule's ground should track the "
        "shared anchor, not the session")
