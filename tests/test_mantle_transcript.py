"""The transcript carries the mantle: a near-black ground with sparse bright dots.

This file REPLACES test_flat_transcript.py, which asserted the opposite. That
contract came from a choice Adam made on 2026-09-13 between a patterned
transcript *with gaps* and a flat one — a false choice, offered while Hermes core
was off-limits. Flat near-black with nothing on it is just a black terminal, and
his verdict on it was immediate: "there is no background displayed especially not
one in cuttlefish style".

With core unlocked the gaps became fixable at the source: prompt_toolkit funnels
every bare `print()` through `StdoutProxy._write`, so one wrapper in `cli.py`
paints the ~46 core call sites that used to punch holes through the skin. The
pattern can therefore come back with TOTAL coverage, which is what these pin.

Assertions are on the RENDERED row, never on a helper, because this theme's
entire bug history is "the helper was right and the surface was still wrong".
"""

from __future__ import annotations

from collections import Counter

import pytest

from cuttlefish_theme.chrome import _MANTLE_GROUND, chrome_renderer
from cuttlefish_theme.color.oklab import hex_to_oklch

SESSIONS = ("tori-main", "zivyra", "tilola", "chef", "wise", "rinera")
SIGNALS = ("resting", "needs_me", "fault")
CORPUS = [f"s{n}" for n in range(200)]


def row(session: str, signal: str = "resting", width: int = 100, row_key: int = 0):
    return chrome_renderer("transcript_line", width,
                           {"session_id": session, "pet_state": signal, "row_key": row_key})


def backgrounds(fragments) -> list[str]:
    return [style.split("bg:")[1].split()[0] for style, _text in fragments]


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
def test_the_transcript_paints(session: str, signal: str) -> None:
    """Every row paints a full-width background. `None` here is the black-terminal bug."""
    fragments = row(session, signal)
    assert fragments, f"{session}/{signal} painted nothing"
    assert sum(len(text) for _style, text in fragments) == 100


@pytest.mark.parametrize("session", SESSIONS)
def test_the_ground_matches_the_terminal_window(session: str) -> None:
    """The mantle's ground IS the OSC 11 colour, so dots read as marks on the window.

    A ground even slightly lighter than the window renders as a panel laid over
    the terminal, with its edges visible wherever painting stops — the "lighter
    box" failure that preceded this design. `pattern._ground` sets #0B0C10 for
    every session; the mantle must agree exactly.
    """
    ground, count = Counter(backgrounds(row(session))).most_common(1)[0]
    assert ground.upper() == _MANTLE_GROUND.upper()
    assert count / 100 >= 0.70, "the ground must dominate; this is a dotted field, not a wash"


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.skip(reason="v17 rule/mantle engine retired by v19; the property is covered by tests/test_v19_integration.py")
def test_dots_are_sparse_and_brighter_than_the_ground(session: str) -> None:
    """Reference renders: 5-25% lit, isolated bright points on near-black."""
    painted = backgrounds(row(session, width=200))
    lit = [c for c in painted if c.upper() != _MANTLE_GROUND.upper()]
    assert 0.02 <= len(lit) / 200 <= 0.25, f"lit fraction {len(lit) / 200:.3f}"
    floor = hex_to_oklch(_MANTLE_GROUND).L
    for colour in lit:
        assert hex_to_oklch(colour).L > floor, "a dot darker than the ground reads as a hole"


@pytest.mark.parametrize("session", SESSIONS)
def test_the_field_is_signal_invariant(session: str) -> None:
    """The surface a user scans to RECOGNISE a window must not move when it alarms.

    Byte-identical across every signal, asserted on the rendered row rather than
    the field helper: a signal-invariant helper behind a signal-sensitive
    renderer satisfies a helper-level test and still flickers on screen. State
    rides the status bar, which is the one surface allowed to change.
    """
    rendered = {signal: row(session, signal, row_key=7) for signal in SIGNALS}
    assert len(set(map(tuple, rendered.values()))) == 1


@pytest.mark.parametrize("session", SESSIONS)
def test_rows_differ_so_the_field_has_vertical_structure(session: str) -> None:
    """A field identical on every row is a stripe, not a mantle."""
    assert len({tuple(row(session, row_key=r)) for r in range(12)}) > 1


@pytest.mark.parametrize("session", SESSIONS)
def test_a_row_is_stable_across_repaints(session: str) -> None:
    """`_replay_output_history()` repaints after a clear; a row must not re-roll."""
    assert row(session, row_key=5) == row(session, row_key=5)


def test_identity_rides_the_dots() -> None:
    """The ground is shared by design, so the DOTS must carry per-session identity.

    Adam, 2026-09-13: "let the dots themselves carry the per-session identity".
    Measured as a rate over a corpus, never one session: a per-session property
    sampled once proves nothing in either direction.
    """
    dot_sets = {
        frozenset(c for c in backgrounds(row(session)) if c.upper() != _MANTLE_GROUND.upper())
        for session in CORPUS
    }
    assert len(dot_sets) >= 40, f"only {len(dot_sets)} distinct dot sets over {len(CORPUS)} sessions"


def test_the_chrome_still_paints() -> None:
    """The mantle must not have displaced the surfaces that carry state."""
    for surface in ("input_rule_top", "input_rule_bot", "status_bar_bg"):
        fragments = chrome_renderer(surface, 100,
                                    {"session_id": "zivyra", "pet_state": "resting"})
        assert fragments, f"{surface} paints nothing"
        assert all("bg:" in style for style, _text in fragments)
