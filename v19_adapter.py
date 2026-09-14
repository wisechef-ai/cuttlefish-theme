"""Adapter: v19's pure engine -> the live Hermes chrome surface.

The engine knows nothing about Hermes. It speaks RGB tuples and its own three
state names. Hermes speaks prompt_toolkit style strings, `PetState` values and
four named surfaces. This module is the only place those two vocabularies meet,
which is what keeps `v19/` reusable and testable on its own.

Dependency direction (Clean Architecture): adapter -> v19. Never the reverse.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .v19 import renderer

# PetState -> the engine's state names. The authoritative values live in the
# CORE enum (agent/pet/constants.py): IDLE/RUN/REVIEW/WAVE/JUMP are quiet,
# WAITING means the turn is paused on the user, FAILED means it stopped.
# Verified at the enum, not inferred: a previous cut of this map invented
# "error"/"awaiting_input", which Hermes never emits, and the alarm channel
# silently rendered as rest.
_PET_STATE_TO_ENGINE: dict[str, str] = {
    "waiting": "attention",
    "failed": "fault",
}

_RESTING = "resting"

# Surfaces the core asks for (hermes_cli/plugins_dispatch.py::_CHROME_SURFACES).
_TRANSCRIPT = "transcript_line"
_STATUS_BAR = "status_bar_bg"
_INPUT_RULES = frozenset({"input_rule_top", "input_rule_bot"})

# The rules are a thin lit strip, so they read as the bar's sibling rather than
# as a slice of transcript: same state channel, one cell tall.
_RULE_GLYPH = "─"
_CELL = " "


def engine_state(pet_state: Any) -> str:
    """Collapse a Hermes ``PetState`` onto one of the engine's three states.

    Unknown, absent and quiet states all resolve to ``resting``: a wrong alarm
    is worse than no alarm, so this fails toward silence.
    """
    return _PET_STATE_TO_ENGINE.get(str(pet_state or "").strip().lower(), _RESTING)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _painted(cells: list[tuple[int, int, int]], glyph: str,
             foreground: tuple[int, int, int] | None = None) -> list[tuple[str, str]]:
    """One prompt_toolkit fragment per cell.

    A surface that OVERLAYS existing fragments must supply the foreground too:
    prompt_toolkit lets the last style win, so returning only ``bg:`` leaves the
    host's stock colour on top of our background.
    """
    if foreground is None:
        return [(f"bg:{_hex(bg)}", glyph) for bg in cells]
    fg = _hex(foreground)
    return [(f"bg:{_hex(bg)} {fg}", glyph) for bg in cells]


@lru_cache(maxsize=4096)
def _transcript_fragments(session_id: str, width: int, row: int) -> tuple[tuple[str, str], ...]:
    """Cached fragments for one transcript row.

    This runs once per printed line, and building a width-long list of
    f-strings per line is most of the cost at that rate: measured 4 us in the
    engine against ~575 us spent re-formatting here. Cache the finished
    fragments, not just the colours.
    """
    cells = renderer.transcript_row(session_id=session_id, width=width, row=row,
                                    time_ms=0.0, occupied=False)
    return tuple(_painted(cells, _CELL))


@lru_cache(maxsize=64)
def _bar_fragments(session_id: str, width: int, state: str, glyph: str) -> tuple[tuple[str, str], ...]:
    """Cached fragments for the state bar and the input rules."""
    cells = renderer.status_bar(session_id=session_id, width=width, state=state)
    return tuple(_painted(cells, glyph, renderer.status_bar_foreground(state)))


def render(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render one chrome surface, or ``None`` to leave it to the host.

    Returns ``None`` only for surfaces this theme does not own or for a context
    too incomplete to identify a session — never as a way of expressing "rest",
    which would inherit the host's stock palette on the one surface that speaks.
    """
    session_id = ctx.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None

    width = int(width)
    if width <= 0:
        return []

    state = engine_state(ctx.get("pet_state"))

    if surface == _TRANSCRIPT:
        row_key = ctx.get("row_key")
        row = row_key if isinstance(row_key, int) and not isinstance(row_key, bool) else 0
        # The transcript is the IDENTITY channel and is signal-invariant by
        # contract: a window's face must not move at the moment it needs you.
        return list(_transcript_fragments(session_id, width, row))

    if surface == _STATUS_BAR:
        # The STATE channel, and the only one. It paints in every state,
        # including rest, or the host falls back to stock gold.
        return list(_bar_fragments(session_id, width, state, _CELL))

    if surface in _INPUT_RULES:
        return list(_bar_fragments(session_id, width, state, _RULE_GLYPH))

    return None


__all__ = ["render", "engine_state"]
