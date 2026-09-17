"""Measured v7 acceptance contract on xterm-256 quantised output."""
from __future__ import annotations

import inspect
import re
from collections import Counter
from itertools import pairwise

import pytest

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.color.terminal import quantize_256
from cuttlefish_theme.linework import separator
from cuttlefish_theme.pattern import render
from cuttlefish_theme.seed import seed_for

CELL = re.compile(r"\[(#[0-9A-Fa-f]{6}) on (#[0-9A-Fa-f]{6})\]")
SESSIONS = ("tori-main", "zivyra", "tilola", "chef", "wise", "session-six")
SIGNALS = ("resting", "needs-me", "fault")
WIDTHS = (40, 80, 200)


def quantised_row(session: str, signal: str, width: int) -> list[int]:
    return [quantize_256(foreground) for foreground, _ in CELL.findall(separator(session, signal, width))]


def mean_run(row: list[int]) -> float:
    runs = 1 + sum(a != b for a, b in pairwise(row))
    return len(row) / runs


def unlit_of(row: list[int]) -> int:
    """The row's OWN unlit colour: its modal entry.

    Not `render(allocate(session)).ground_hex`. That near-black stopped being
    this surface's floor when the unlit cells moved into the session's readable
    band, and a metric still referencing it counts every cell as vivid (measured:
    vivid_share 1.0 against a 0.38 ceiling) — the surface looks broken while it
    is the yardstick that moved. Read the fill from the rendered row.
    """
    return Counter(row).most_common(1)[0][0]


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
@pytest.mark.parametrize("width", WIDTHS)
def test_quantised_rule_meets_measured_grammar(session: str, signal: str, width: int) -> None:
    row = quantised_row(session, signal, width)
    ground = unlit_of(row)
    modal_share = Counter(row).most_common(1)[0][1] / width
    vivid_share = sum(colour != ground for colour in row) / width

    assert len(row) == width
    assert modal_share >= 0.55
    # 0.08-0.20 was read off a 2D Metasepia patch. Re-applied to ONE row it left
    # voids the eye read as emptiness (measured: a 33-cell dark gap on an
    # 80-column rule; Adam: "very scattered with a lot of black spaces"), so
    # this floor was raised to 0.22 and the surface painted ~0.30.
    #
    # RE-POINTED 2026-09-13. That reasoning assumed the unlit cells were a
    # TRENCH — a near-black the eye read as a hole — so density was the only
    # way to hide them. It no longer holds: `_unlit` now paints one flat
    # mid-dark ground under the whole rule and every dot sits ON that ground,
    # so a gap between dots is more ground rather than a void. With the trench
    # gone, the 2D reference figure is reachable on one row after all, and the
    # eight design renders Adam is working from measure 5-25% lit
    # (docs/reference-structure.md).
    #
    # The floor moves to 0.15 rather than to the reference's 0.05 because the
    # budget is spent per 10-column segment (`round(f * 10)`), so the reachable
    # values are 0.1, 0.2, 0.3...: 0.15 admits the 2-dots-per-10 the surface now
    # paints while still failing a surface that drops to one.
    #
    # Cost, measured and accepted: distinct rendered rule signatures over 200
    # sessions fall from 64 to 39, because sparser dots mean fewer distinct
    # quantised dot-sets. Identity still rides the dots (their class-set carries
    # 113 distinct values); the ground is deliberately near-uniform.
    assert 0.15 <= vivid_share <= 0.38
    assert mean_run(row) >= 2.0
    # No void may swallow the pattern. The bound is arithmetic, not taste: with
    # S-column segments and k picks each, two picks at opposite ends of adjacent
    # segments sit at most 2*(S-k) apart. The surface uses S=10 and
    # k=round(_VIVID_FRACTION*10), so the bound MOVES WITH THE DENSITY — it was
    # 14 at k=3 (vivid 0.30) and is 16 at k=2 (vivid 0.20, set 2026-09-13).
    #
    # Derive it here rather than hardcoding, so the next density change cannot
    # leave a stale number that either passes a genuine void or fails correct
    # output. Measured worst case across every session/signal/width equals the
    # bound exactly, which is what "structural" means: it is reached, not
    # approached.
    from cuttlefish_theme.linework import _VIVID_FRACTION
    segment = 10
    bound = 2 * (segment - max(1, round(_VIVID_FRACTION * segment)))
    gap = max(len(run) for run in "".join(
        "." if colour == ground else "#" for colour in row).split("#")) if any(
        colour != ground for colour in row) else width
    assert gap <= bound, f"longest dark gap {gap} exceeds the structural bound {bound}"


def test_fault_is_never_a_flat_line_and_has_sparse_vivid_cells() -> None:
    row = quantised_row("tori-main", "fault", 80)
    ground = quantize_256(render(allocate("tori-main")).ground_hex)
    assert len(set(row)) >= 3
    assert sum(colour != ground for colour in row) / len(row) >= 0.08


def test_input_rule_is_driven_by_body_pattern_field_not_modulo_rainbow() -> None:
    import cuttlefish_theme.linework as linework
    from cuttlefish_theme.patterns import field_for

    assert field_for("zivyra", 120, 1)[0].name in {
        "uniform-fine-mottle", "coarse-mottle", "transverse-stripes-zebra",
        "passing-cloud-bands", "disruptive-patches", "pearl-scatter",
    }
    source = inspect.getsource(linework)
    assert "field_for" in source
    assert "% len(" not in source


def test_sessions_and_signals_remain_distinguishable_and_stable() -> None:
    resting_a = quantised_row("zivyra", "resting", 160)
    assert resting_a == quantised_row("zivyra", "resting", 160)
    assert resting_a != quantised_row("tilola", "resting", 160)
    assert resting_a != quantised_row("zivyra", "needs-me", 160)
    assert resting_a != quantised_row("zivyra", "fault", 160)
    assert seed_for("zivyra") == seed_for("zivyra")


def _vivid_indices(session: str, signal: str, width: int = 200) -> set[int]:
    pairs = CELL.findall(separator(session, signal, width))
    ground = quantize_256(pairs[0][1])
    return {quantize_256(fg) for fg, _ in pairs if quantize_256(fg) != ground}


def _xterm_oklch(index: int):
    from cuttlefish_theme.color.oklab import hex_to_oklch
    from cuttlefish_theme.color.terminal import _index_to_hex
    return hex_to_oklch(_index_to_hex(index))


def test_acute_input_rule_uses_quantised_amber_and_red_without_identity_mix() -> None:
    for session in ("zivyra", "tilola", "chef"):
        resting = _vivid_indices(session, "resting")
        needs_me = _vivid_indices(session, "needs-me")
        fault = _vivid_indices(session, "fault")
        assert needs_me and fault
        assert all(62 <= _xterm_oklch(i).h <= 105 for i in needs_me)
        assert all(5 <= _xterm_oklch(i).h <= 48 for i in fault)
        assert len(needs_me & resting) / len(needs_me) <= 0.20
        assert len(fault & resting) / len(fault) <= 0.20


def test_ten_sessions_have_distinct_vivid_pigment_sets_and_separated_accents() -> None:
    """Distinct pigment sets per session, and accents that stay apart.

    THE EXACT-DISTINCTNESS ARM IS NOW A RATE, and the reason is arithmetic
    rather than a tuning failure. `_VIVID_FRACTION` dropped to 0.20 on
    2026-09-13 to match the reference renders' 5-25% lit, which spends 2 dots
    per 10 columns instead of 3. Fewer dots sample fewer of the session's
    pigment variants, and after quantisation the surviving sets collide:
    measured over a 200-session corpus, 37 distinct sets at every width tested
    (40/80/200), with 188 of 200 sessions sharing a set with someone.

    `== len(sessions)` on a 10-session sample is therefore unsatisfiable — it
    passed before only because a denser rule sampled more variants. Asserting it
    anyway would invite the next agent to "fix" it by putting the density back,
    undoing the change Adam asked for.

    So this pins what is real and still load-bearing: a floor on distinct sets
    over a CORPUS (a rate, not a single sample), plus the accent separation,
    which sparsity does not affect. The known ceiling is recorded above so the
    number is not mistaken for a target anyone should tune toward.
    """
    from cuttlefish_theme.color.oklab import delta_e_ok

    corpus = [f"s{n}" for n in range(200)]
    corpus_sets = {frozenset(_vivid_indices(session, "resting")) for session in corpus}
    assert len(corpus_sets) >= 30, (
        f"only {len(corpus_sets)} distinct pigment sets over {len(corpus)} sessions")

    sessions = ("tori-main", "zivyra", "tilola", "chef", "wise", "session-six",
                "mantis", "adam-chef-01", "alpha", "beta")
    sets = [_vivid_indices(session, "resting") for session in sessions]
    assert min(max(delta_e_ok(_xterm_oklch(a), _xterm_oklch(b))
                   for a in left for b in right)
               for i, left in enumerate(sets) for right in sets[i + 1:]) >= 0.170


def test_rule_preserves_width_and_rich_parseability() -> None:
    from rich.text import Text

    for width in (0, 1, 7, 79, 200):
        text = Text.from_markup(separator("zivyra", "resting", width))
        assert text.cell_len == width
