"""INTEGRATION CONTRACT — v19 reaches the live CLI. LOCKED.

Authored by Tori. THE IMPLEMENTER MUST NOT EDIT THIS FILE.

WHY THIS FILE EXISTS
--------------------
v19 passes 42 behavioural outcomes and renders well, and NOTHING IN THE LIVE
PLUGIN CALLS IT. `chrome_renderer` in chrome.py still drives the v17 engine, so
a user typing `hermes` sees none of this work.

That failure has a name in this project's history: core passed `row_key` while
the plugin required `session_id`, so both halves were green and the feature
painted nothing end to end. A contract that only tests the engine cannot see it.

This file asserts the WIRING: that the function Hermes actually calls returns
v19's colours, on the surfaces Hermes actually asks for, in the shape
prompt_toolkit actually accepts.

THE SEAM, verified in hermes-agent:
    cli.py:1718,1785            manager.render_chrome("transcript_line", ...)
    cli_status_bar_mixin:1125   render_chrome("status_bar_bg", ...)
    plugins_dispatch.py:26      _CHROME_SURFACES = {input_rule_top,
                                input_rule_bot, status_bar_bg, transcript_line}

RUN:  cd ~/.hermes/plugins/cuttlefish-theme && make test
"""

from __future__ import annotations

import re

import pytest

from cuttlefish_theme import chrome

v19 = pytest.importorskip("cuttlefish_theme.v19", reason="v19 port not yet implemented")
from cuttlefish_theme.v19 import renderer  # noqa: E402

SID = "integration-session-001"
SURFACES = ("transcript_line", "status_bar_bg", "input_rule_top", "input_rule_bot")

# The pet_state values Hermes ACTUALLY emits (agent/pet/constants.py:59-65).
# A first cut of this file invented "error"/"awaiting_input" and read the
# resulting single-colour bar as a dead state channel; the plugin was right
# and the test was wrong. Verify names at the producing enum, never guess.
RESTING, ATTENTION, FAULT = "idle", "waiting", "failed"

_HEX = re.compile(r"#([0-9A-Fa-f]{6})")


def _ctx(**kw):
    base = {"session_id": SID, "row_key": 3, "pet_state": "idle"}
    base.update(kw)
    return base


def _render(surface, width=80, **kw):
    return chrome.chrome_renderer(surface, width, _ctx(**kw))


def _bgs(fragments):
    """Background hex of each fragment, as prompt_toolkit would read it."""
    out = []
    for style, _text in fragments:
        m = re.search(r"bg:#([0-9A-Fa-f]{6})", style)
        out.append(m.group(1).lower() if m else None)
    return out


def _rgb(hex6):
    return tuple(int(hex6[i:i + 2], 16) for i in (0, 2, 4))


# ===========================================================================
# 1. The live renderer answers every surface Hermes asks for.
# ===========================================================================

class TestLiveSurfaces:
    @pytest.mark.parametrize("surface", SURFACES)
    def test_every_core_surface_paints(self, surface):
        assert _render(surface), f"{surface} returned nothing — core falls back to stock gold"

    @pytest.mark.parametrize("surface", SURFACES)
    def test_fragments_are_prompt_toolkit_shaped(self, surface):
        for style, text in _render(surface):
            assert isinstance(style, str) and isinstance(text, str)
            assert "[" not in style, "Rich markup renders styleless in prompt_toolkit"

    @pytest.mark.parametrize("surface", SURFACES)
    def test_width_is_honoured_exactly(self, surface):
        for width in (1, 17, 80, 200):
            cells = _render(surface, width=width)
            assert sum(len(t) for _s, t in cells) == width, f"{surface} @ {width}"

    def test_an_unknown_surface_declines_rather_than_crashing(self):
        assert _render("not_a_surface") is None

    def test_a_missing_session_id_declines(self):
        assert chrome.chrome_renderer("transcript_line", 40, {"row_key": 1}) is None


# ===========================================================================
# 2. The live renderer is actually driven by v19 — not by a parallel engine.
# ===========================================================================

class TestV19IsTheEngine:
    def test_transcript_colours_come_from_v19(self):
        live = _bgs(_render("transcript_line", width=60))
        expected = [f"{r:02x}{g:02x}{b:02x}" for r, g, b in
                    renderer.transcript_row(session_id=SID, width=60, row=3,
                                            time_ms=0, occupied=False)]
        assert live == expected, "the live transcript does not match v19's output"

    def test_status_bar_colours_come_from_v19(self):
        live = _bgs(_render("status_bar_bg", width=40))
        expected = [f"{r:02x}{g:02x}{b:02x}" for r, g, b in
                    renderer.status_bar(session_id=SID, width=40, state="resting")]
        assert live == expected, "the live status bar does not match v19's output"


# ===========================================================================
# 3. THE LANGUAGE, enforced on the LIVE path (not just in the engine).
# ===========================================================================

class TestLanguageOnTheLivePath:
    def test_the_transcript_never_moves_on_a_state_change(self):
        """Identity channel: the surface you scan to FIND a window must not
        change at the moment that window needs you."""
        resting = _bgs(_render("transcript_line", pet_state="idle"))
        for state in ("waiting", "failed", "run", "review"):
            assert _bgs(_render("transcript_line", pet_state=state)) == resting, \
                f"pet_state={state} moved the identity surface"

    def test_the_bar_reads_identically_across_sessions(self):
        """State channel: an alarm that differs per window is not an alarm."""
        for state in ("idle", "waiting", "failed"):
            bars = {tuple(_bgs(chrome.chrome_renderer(
                "status_bar_bg", 40,
                {"session_id": f"sess-{n}", "row_key": 0, "pet_state": state})))
                for n in range(8)}
            assert len(bars) == 1, f"state {state} rendered {len(bars)} ways"

    def test_the_two_alarms_differ_from_rest_and_from_each_other(self):
        rest = _bgs(_render("status_bar_bg", pet_state="idle"))[0]
        attention = _bgs(_render("status_bar_bg", pet_state="waiting"))[0]
        fault = _bgs(_render("status_bar_bg", pet_state="failed"))[0]
        assert len({rest, attention, fault}) == 3

    def test_different_sessions_get_different_faces(self):
        faces = {tuple(_bgs(chrome.chrome_renderer(
            "transcript_line", 40, {"session_id": f"s{n}", "row_key": 1, "pet_state": "idle"})))
            for n in range(12)}
        assert len(faces) >= 11, f"only {len(faces)} distinct faces in 12 sessions"


# ===========================================================================
# 4. Cheap enough to sit on a scrolling transcript.
# ===========================================================================

class TestLiveCost:
    def test_a_repeated_row_is_effectively_free(self):
        import time
        _render("transcript_line", width=200)
        start = time.perf_counter()
        for _ in range(500):
            _render("transcript_line", width=200)
        per_call_us = (time.perf_counter() - start) / 500 * 1e6
        assert per_call_us < 400, f"{per_call_us:.0f} us/row on the live path"


# ===========================================================================
# 5. Fails closed. A themed terminal must never be a broken terminal.
# ===========================================================================

class TestFailsClosed:
    @pytest.mark.parametrize("bad", [
        {"session_id": "", "row_key": 0},
        {"session_id": SID, "row_key": "not-an-int"},
        {"session_id": SID},
        {},
    ])
    def test_malformed_context_never_raises(self, bad):
        for surface in SURFACES:
            chrome.chrome_renderer(surface, 40, bad)

    @pytest.mark.parametrize("width", [0, -1, 1, 5000])
    def test_absurd_widths_never_raise(self, width):
        for surface in SURFACES:
            chrome.chrome_renderer(surface, width, _ctx())
