"""The bar's unlit colour must sit in the session's band, not in a trench.

v13 moved the mantle's ground into the session's readable band, but the input
rule kept painting its unlit cells the pre-v13 near-black (#0B0C10, OKLab
L .155). With 70% of columns unlit, most of the bar sat ~0.15 L below its own
pigments and the eye read that as holes punched in the skin — Adam, 2026-09-11:
"can we make it all colored - without black gaps?"

Filling every column instead is the WRONG fix and has its own guard here: it
takes dominance to 0.25 against a 0.55 contract, i.e. it removes the gaps by
deleting the pattern.

These assertions are deliberately about the GAP BETWEEN unlit and lit, because
the grammar tests measure each row against its own modal colour and therefore
cannot see a uniformly-sunken floor.
"""

from __future__ import annotations

from collections import Counter

import pytest

from cuttlefish_theme.band import band
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.linework import _unlit, cells

SESSIONS = ("tori-main", "zivyra", "tilola", "chef", "wise", "session-six", "rinera")
SIGNALS = ("resting", "needs-me", "fault")

# The pre-v13 near-black this surface was stranded on.
TRENCH = "#0B0C10"


def unlit_in_row(session: str, signal: str, width: int = 80) -> str:
    """The unlit colour AS RENDERED — the modal background of the actual row.

    Not `_unlit(...)` directly. The defect was at the call site: `cells` computed
    its ground from the pre-v13 near-black while the helper was correct, so a
    test that asks the helper passes on broken output. Read what the bar paints.
    """
    row = cells(session, signal, width)
    return Counter(foreground for foreground, _bg, _glyph in row).most_common(1)[0][0]


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
def test_unlit_is_not_the_pre_v13_near_black(session: str, signal: str) -> None:
    assert unlit_in_row(session, signal).upper() != TRENCH


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
def test_unlit_is_inside_the_band_not_below_it(session: str, signal: str) -> None:
    """The floor must not sink beneath the band the session lives in.

    Deliberately NOT "lit cells sit near the unlit one": the rule is a LIT strip
    (`_BAR_L` ramps 0.50-0.80), so a wide unlit-to-lit gap is the design. What
    made it read as holes was the floor sitting 0.15 L BELOW the band entirely.
    An assertion on the gap would fail on correct output — the defect is the
    floor's absolute position, so that is what is pinned.
    """
    floor = min(hex_to_oklch(colour).L for colour in band())
    assert hex_to_oklch(unlit_in_row(session, signal)).L >= floor - 0.005


@pytest.mark.parametrize("signal", SIGNALS)
def test_every_wire_form_signal_resolves(signal: str) -> None:
    """`cells` takes wire-form signals; Signal's values are canonical.

    Passing the wire form into a Signal(...) lookup raises ValueError inside a
    repaint, which `chrome_renderer` swallows as None — the bar reverts to stock
    on exactly the states that matter, silently.
    """
    assert _unlit("zivyra", signal)
    assert len(cells("zivyra", signal, 80)) == 80


def test_error_is_an_alias_of_fault() -> None:
    assert _unlit("zivyra", "error") == _unlit("zivyra", "fault")
