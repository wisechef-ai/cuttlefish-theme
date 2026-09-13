"""The transcript is FLAT: the theme paints no per-line background at all.

Adam, 2026-09-13, choosing between a patterned transcript and a still one:
"flat near-black behind the transcript (no pattern, no shimmer, no gaps) — all
the art lives on the fixed rules/bar".

Three defects closed by that one deletion, and each gets an assertion here so a
future "let's put the mantle back" has to argue with a red test:

1. THE GAPS. The mantle reached only lines routed through `cli.py::_cprint`;
   core's ~39 bare `print()` calls in `agent/` never enter that seam and so
   rendered on raw terminal background between tinted neighbours. A surface
   that paints SOME lines is strictly worse than one that paints none, because
   the eye reads the unpainted ones as holes. Painting nothing is uniform by
   construction — no call-site audit required, in a repo we do not own.

2. THE SCROLL. A per-line background is glued to its text and moves with it.
   VTE has no layer behind the cell grid, so "still background" and "patterned
   transcript" cannot both be true.

3. THE WASH. Measured at the time of the change (tools/measure_vs_reference.py,
   40 sessions): mantle ground OKLab L .301 against the reference renders'
   .05-.10, 30% of cells lit against their 5-25%, 4.5 distinct tones against
   their 7-15.

These assert the RENDERER's output, not the helper's: `_mantle_row` may well
survive as dead-ish code for the `watch`/preview surfaces, and a test asking it
would pass while the transcript was still being painted.
"""

from __future__ import annotations

import pytest

from cuttlefish_theme.chrome import chrome_renderer

SESSIONS = ("tori-main", "zivyra", "tilola", "chef", "wise", "rinera")
SIGNALS = ("resting", "needs_me", "fault")
CHROME_SURFACES = ("input_rule_top", "input_rule_bot", "status_bar_bg")


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
@pytest.mark.parametrize("row_key", (0, 1, 7, 23))
def test_transcript_line_is_never_painted(session: str, signal: str, row_key: int) -> None:
    """`None` hands the line back to the terminal's own OSC 11 background.

    Every row key, because the defect this replaces was row-keyed: the pattern
    varied down the screen, which is exactly what made unhooked lines legible
    as holes rather than as more of the same.
    """
    assert chrome_renderer("transcript_line", 100,
                           {"session_id": session, "pet_state": signal,
                            "row_key": row_key}) is None


@pytest.mark.parametrize("session", SESSIONS)
def test_transcript_is_flat_across_every_row_and_signal(session: str) -> None:
    """One session, every row and signal: a single unpainted answer.

    The per-parameter test above could pass while some (row, signal) pair still
    painted; this collapses the whole space to one value so a partially-restored
    mantle cannot hide in a corner of it.
    """
    answers = {chrome_renderer("transcript_line", width,
                               {"session_id": session, "pet_state": signal, "row_key": row})
               for signal in SIGNALS for row in range(40) for width in (40, 100, 200)}
    assert answers == {None}


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
def test_the_art_still_lives_on_the_chrome(session: str, signal: str) -> None:
    """The deletion must not silently uninstall the theme.

    A renderer returning None everywhere would pass the tests above and leave
    the user with stock Hermes gold — the failure mode §6f-ter of the authoring
    skill exists to prevent. The surfaces that HOLD STILL must still paint.
    """
    for surface in CHROME_SURFACES:
        fragments = chrome_renderer(surface, 100,
                                    {"session_id": session, "pet_state": signal})
        assert fragments, f"{surface} paints nothing for {session}/{signal}"
        assert all("bg:" in style for style, _text in fragments)
