"""The background is identity; only the bar carries state.

Adam, 2026-09-12: "per session the colors dominants should only change if there
is pet reaction changing the change should not affect the background - the
background change makes the recognition of terminal harder".

The first truecolor cut repainted the whole mantle amber on `needs_me` and red
on `fault`. That inverts the purpose of the two channels: the surface you use to
RECOGNISE a window changed at the exact moment that window had something to say,
so you lost the terminal when you most needed to find it. The field is now
signal-invariant and the bar is the only thing that moves.
"""

from __future__ import annotations

import pytest

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.ribbon import bar_cells, ribbon_field, ribbon_row

_SESSIONS = [f"s{n}" for n in range(24)]
_SIGNALS = ("resting", "needs_me", "fault")


@pytest.mark.parametrize("session_id", _SESSIONS)
def test_the_mantle_is_byte_identical_across_every_signal(session_id):
    """The background must not move when state changes. This is the whole rule."""
    fields = {s: ribbon_field(session_id, 80, 12, s) for s in _SIGNALS}
    assert fields["needs_me"] == fields["resting"], (
        f"{session_id}: needs_me repainted the background — the window becomes "
        "unrecognisable exactly when it needs attention"
    )
    assert fields["fault"] == fields["resting"], (
        f"{session_id}: fault repainted the background"
    )


@pytest.mark.parametrize("session_id", _SESSIONS[:8])
def test_the_row_renderer_agrees_with_the_field(session_id):
    """The per-line path is what the terminal actually calls; pin it too.

    A signal-invariant `ribbon_field` with a signal-sensitive `ribbon_row` would
    satisfy the rule in tests and break it on screen.
    """
    for row in range(6):
        rendered = {s: ribbon_row(session_id, 80, row, s) for s in _SIGNALS}
        assert rendered["needs_me"] == rendered["resting"]
        assert rendered["fault"] == rendered["resting"]


@pytest.mark.parametrize("session_id", _SESSIONS[:8])
def test_the_bar_carries_the_state_the_background_no_longer_does(session_id):
    """Removing state from the field is only safe if the bar still shows it."""
    resting, needs_me, fault = (bar_cells(session_id, 80, s) for s in _SIGNALS)
    assert needs_me != resting, f"{session_id}: needs_me is invisible — no channel shows it"
    assert fault != resting, f"{session_id}: fault is invisible"
    assert needs_me != fault, f"{session_id}: the two alarms are indistinguishable"


def test_the_alarm_bar_is_identical_in_every_window():
    """An alarm that differs per session cannot be read across six terminals."""
    for signal in ("needs_me", "fault"):
        rendered = {bar_cells(s, 80, signal) for s in _SESSIONS}
        assert len(rendered) == 1, (
            f"{signal} renders {len(rendered)} different bars across "
            f"{len(_SESSIONS)} sessions — the alarm means something different "
            "in each window"
        )


def test_the_resting_bar_belongs_to_its_own_session():
    """At rest the bar is identity, so it must differ between sessions."""
    rendered = {bar_cells(s, 80, "resting") for s in _SESSIONS}
    assert len(rendered) >= len(_SESSIONS) * 0.75, (
        f"only {len(rendered)} distinct resting bars over {len(_SESSIONS)} sessions"
    )


@pytest.mark.parametrize(
    "signal,low,high",
    [("fault", 350.0, 410.0), ("needs_me", 55.0, 115.0)],
)
def test_each_alarm_owns_its_own_hue_arc(signal, low, high):
    """Fault reads red, needs_me reads amber, and the arcs must not overlap.

    A first cut spanned 4-68 and 38-86 degrees: the two alarms shared 38-68, so
    "failed" was unreadable against "waiting".
    """
    for _fg, background, _glyph in bar_cells("any-session", 80, signal):
        hue = hex_to_oklch(background).h
        assert low <= hue <= high or low <= hue + 360.0 <= high, (
            f"{signal} painted hue {hue:.1f}, outside its {low}-{high} arc"
        )
