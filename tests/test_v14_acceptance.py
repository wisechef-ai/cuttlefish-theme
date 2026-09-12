"""v14 acceptance: only a WATCHED session paints, and every surface agrees on a hue.

Two defects motivate this file, both found by measuring the live skin file rather
than the renderer:

1. CRON SESSIONS REPAINT THE STABLE SKIN. `on_session_start` writes the stable
   `cuttlefish.yaml` — the file `display.skin` resolves — for EVERY session, and a
   cron fire is a session. Measured on adam-xps: the stable skin changed owner
   three times in 120 seconds, none of them the interactive session. The user has
   therefore never seen their own session's identity; they see whichever headless
   job woke last. Every aesthetic fix is overwritten within a minute by a job
   nobody is watching.

2. THE SURFACES DO NOT SHARE A HUE. The `colors:` block, the input rule and the
   banner hero each derive their own hue independently. Measured on the live file:
   colors: block 24/38 keys at hue 140 (green), bar fill #000087 (blue), hero
   spanning blue/green/pink/violet/teal/olive — zero hue families shared by all
   three. That is the "looks ugly" the user reported, and no prior contract
   measured across surfaces, which is why the suite stayed green through it.
"""

from __future__ import annotations

from collections import Counter

import pytest

from cuttlefish_theme import plugin as plugin_mod
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.skinio import stable_skin_name

_FAMILY_ARC = 60.0

# Below this chroma a colour reads as grey and carries no hue information, so it
# is exempt from coherence — the ground, the body text and the dim label are
# deliberately near-neutral.
_MIN_CHROMA = 0.030


def _family(hex_colour: str) -> int | None:
    """Which hue family a colour belongs to, or None when it reads as grey."""
    c = hex_to_oklch(hex_colour)
    if c.C < _MIN_CHROMA:
        return None
    return int(c.h // _FAMILY_ARC) % int(360 // _FAMILY_ARC)


# --------------------------------------------------------------------------
# Outcome 1 — a headless session must not repaint the watched terminal
# --------------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["cron", "telegram", "discord", "gateway", "api"])
def test_a_headless_session_never_paints(platform):
    """Only a surface with a human watching may claim the stable skin.

    The stable skin is a SHARED resource: one file, many sessions. A session with
    no terminal attached cannot see what it paints, so painting can only ever
    corrupt somebody else's view.
    """
    assert not plugin_mod.paints(platform), (
        f"platform {platform!r} has no attached terminal but is allowed to paint "
        "the stable skin, which overwrites the interactive session's identity"
    )


@pytest.mark.parametrize("platform", ["cli", "tui", "desktop", ""])
def test_a_watched_session_still_paints(platform):
    """The guard must not be so wide that the real terminal stops being themed.

    The empty platform is the unknown case and must paint: an older Hermes that
    does not pass `platform` at all is an interactive CLI, and failing closed
    there would uninstall the theme for everyone on that version.
    """
    assert plugin_mod.paints(platform), (
        f"platform {platform!r} is a watched surface and must still be themed"
    )


def test_a_cron_session_start_writes_no_skin_and_starts_no_animator(tmp_path, monkeypatch):
    """End to end: the hook itself must be inert for a headless session.

    Asserted on the real `on_session_start`, not on the predicate, because the
    defect was never in a predicate — it was that the hook had no notion of who
    was watching.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skins = tmp_path / "skins"
    skins.mkdir(parents=True)
    stable = skins / f"{stable_skin_name()}.yaml"
    stable.write_text("name: sentinel\n")

    plugin_mod.on_session_start(session_id="cron_deadbeef_20260912_120000",
                                platform="cron")

    assert stable.read_text() == "name: sentinel\n", (
        "a cron session overwrote the stable skin the interactive terminal reads"
    )
    assert plugin_mod._state.get("animator") is None, (
        "a cron session started a repaint animator for a terminal nobody is watching"
    )


def test_a_cron_session_end_does_not_reset_the_terminal_background(monkeypatch):
    """A headless end must not emit OSC 11 either.

    `on_session_end` resets the terminal background unconditionally. When a cron
    fires inside a terminal's process tree that escape sequence lands on the
    USER's emulator and wipes the background the interactive session set.
    """
    calls = []
    monkeypatch.setattr(plugin_mod, "reset_terminal_background",
                        lambda: calls.append("reset"))

    plugin_mod.on_session_end(session_id="cron_deadbeef_20260912_120000",
                              platform="cron")

    assert calls == [], "a cron session reset the watched terminal's background"


# --------------------------------------------------------------------------
# Outcome 2 — one session, one hue budget, across every surface
# --------------------------------------------------------------------------

_SESSIONS = [f"s{n}" for n in range(40)]

# Keys whose colour is UNIVERSAL by design and must never take the session hue:
# the semantic states (an error is red in every session, exactly like the acute
# signals) and the near-neutral text roles. Folding these into a coherence
# measurement would demand that a green "ok" tick turn violet to match its
# window — which would destroy the semantics coherence exists to protect.
_UNIVERSAL_KEYS = frozenset({
    "status_bar_good", "status_bar_warn", "status_bar_bad", "status_bar_critical",
    "ui_ok", "ui_warn", "ui_error",
    "syntax_string", "syntax_number", "syntax_keyword", "syntax_comment",
})


def _surfaces(session_id: str) -> dict[str, list[str]]:
    """Every colour a session shows, grouped by the surface that shows it.

    Weighted by what the terminal actually renders, not by distinct colour: the
    mantle carries a few island colours that occupy ~18% of cells by contract, so
    counting colours instead of cells reports 50% dominance for a field the eye
    reads as one hue.
    Every surface is read through the PRODUCTION path. An earlier version of this
    file called `build_palette` directly and so bypassed `Palette.skin_colors`,
    where the session's hue is actually applied — it measured a function no
    terminal ever calls and reported an incoherence the product did not have.
    """
    from cuttlefish_theme.chrome import _mantle_row
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.linework import cells
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.session import Signal

    palette = render(allocate(session_id), Signal.RESTING).skin_colors()
    width, rows = 80, 12
    return {
        "palette": [v for k, v in palette.items() if k not in _UNIVERSAL_KEYS],
        "bar": [bg for _fg, bg, _glyph in cells(session_id, "resting", width)],
        "mantle": [style.split("bg:")[1].split()[0]
                   for row in range(rows)
                   for style, _text in _mantle_row(session_id, width, row, "resting")
                   if "bg:" in style],
    }


@pytest.mark.parametrize("session_id", _SESSIONS)
def test_every_surface_shares_the_session_dominant_family(session_id):
    """The bar, the mantle and the palette must speak ONE hue family.

    This is the contract nothing measured before. Each surface derived its hue
    from its own hash, so a session could wear a green palette, a blue bar and a
    six-hue hero simultaneously — three themes in one window.
    """
    families = _surface_families(session_id)
    shared = set.intersection(*families.values()) if families else set()
    assert shared, (
        f"session {session_id} shares NO hue family across its surfaces: "
        + ", ".join(f"{name}={sorted(f)}" for name, f in families.items())
    )


def _surface_families(session_id: str) -> dict[str, set[int]]:
    """Each surface's hue families, greys dropped."""
    return {name: {f for f in map(_family, colours) if f is not None}
            for name, colours in _surfaces(session_id).items()}


@pytest.mark.parametrize("session_id", _SESSIONS)
def test_the_dominant_family_actually_dominates_each_surface(session_id):
    """Sharing one colour is not coherence; the shared family must carry the surface.

    A bar that is 15/16 blue with one green cell "shares" green with a green
    palette while still reading as a blue bar. The shared family has to be the
    majority of each surface's chromatic colours for the window to read as one
    skin.
    """
    surfaces = _surfaces(session_id)
    counts = Counter(f for colours in surfaces.values()
                     for f in map(_family, colours) if f is not None)
    assert counts, f"session {session_id} has no chromatic colour at all"
    dominant = counts.most_common(1)[0][0]

    for name, colours in surfaces.items():
        chromatic = [f for f in map(_family, colours) if f is not None]
        if not chromatic:
            continue
        share = chromatic.count(dominant) / len(chromatic)
        assert share >= 0.60, (
            f"session {session_id} surface {name!r}: only {share:.0%} of its "
            f"chromatic colours are in the session's dominant family {dominant} "
            "— the surfaces read as different themes"
        )


def test_sessions_still_differ_after_coherence():
    """Coherence must not collapse every session onto one look.

    The cheap way to pass the two contracts above is to give every session the
    same colours, which would fix "ugly" by deleting identity.

    Identity is asserted on the PALETTE, not the family count, because the family
    count is arithmetic and not a design choice: the readable dark band holds
    nine cube entries in three hue families, one of which is the alarm — so a
    resting session has exactly TWO families to choose from and no implementation
    can produce more. Asserting >= 4 there would be demanding the impossible and
    would eventually be "fixed" by letting red back into the resting set, which
    is the defect this work removed.

    What must stay varied is the full palette: which shades of the family, which
    islands, in which order. That is where the real separation lives, and it is
    what stops two windows looking alike.
    """
    from cuttlefish_theme.chrome import _dominant_palette, dominant_hue

    families_seen = {int(dominant_hue(s) // _FAMILY_ARC) for s in _SESSIONS}
    palettes = {_dominant_palette(s) for s in _SESSIONS}

    assert len(families_seen) >= 2, (
        f"only {len(families_seen)} dominant family over {len(_SESSIONS)} sessions "
        "— every window would wear one hue"
    )
    assert len(palettes) >= len(_SESSIONS) * 0.5, (
        f"only {len(palettes)} distinct palettes over {len(_SESSIONS)} sessions "
        "— coherence was bought by deleting identity"
    )
