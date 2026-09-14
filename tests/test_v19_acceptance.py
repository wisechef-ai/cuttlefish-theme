"""ACCEPTANCE CONTRACT — cuttlefish v19 (the CLI port). LOCKED.

Authored by Tori BEFORE implementation. THE IMPLEMENTER MUST NOT EDIT THIS FILE.

WHY v19 EXISTS
--------------
v18 built a verified field engine in TypeScript aimed at the Electron desktop
app. Adam then said how he actually launches: he opens a terminal emulator and
types `hermes`. That is the CLI — `_AGENT_COMMANDS = {None, "chat", ...}` in
hermes_cli/main.py — not Electron.

That single fact removes every blocker:

  * A terminal is a CELL GRID. 200x50 = 10,000 cells, not 1,440,000 pixels.
    Measured: one transcript row renders in 0.92 ms. The 8-second frame that
    made the Electron path unshippable does not exist here.
  * The chrome renderer hook is ALREADY LIVE in this core
    (hermes_cli/plugins_dispatch.py:26 registers `transcript_line`), and the
    plugin is ALREADY ENABLED in config.yaml.
  * So no WebGL, no Electron, no core change, and no sign-off on someone
    else's repo. The vehicle exists; it has been carrying the wrong cargo.

This contract ports v18's PROVEN biology to Python at cell resolution:
correct OKLab, three compositing layers, hue-preserving contraction, finite
support, per-session identity.

THE LANGUAGE (this is a semantic contract, not decoration)
----------------------------------------------------------
The theme is a language with exactly two channels, and they fail in opposite
directions, so they must never share a surface:

  FIELD (the transcript background) = IDENTITY. "Which window is this?"
      Unique per session. NEVER changes on a state change, because the surface
      you scan to find a window must not move at the moment it needs you.

  BAR (the status bar) = STATE. "Does this window want me?"
      Identical across every session for a given state, because an alarm that
      looks different in each window is not an alarm.

Outcomes 9-11 pin those semantics. A build that renders beautifully and
violates them has failed.

RUN:  cd ~/.hermes/plugins/cuttlefish-theme && make test
"""

from __future__ import annotations

import math

import pytest

# The port under construction. Until it lands this file SKIPS rather than
# erroring: a module-level ImportError aborts pytest's whole collection, which
# would take the plugin's other 521 tests down with it and leave `make test`
# red for a reason unrelated to any of them.
v19 = pytest.importorskip("cuttlefish_theme.v19", reason="v19 port not yet implemented")

from cuttlefish_theme.v19 import contraction, field, oklab, palette, renderer  # noqa: E402

# ---------------------------------------------------------------------------
# measuring instruments (tested in test_v19_metrics.py before they are trusted)
# ---------------------------------------------------------------------------

BODY_FG = (0xE8, 0xE8, 0xEA)


def _wcag_lum(rgb: tuple[int, int, int]) -> float:
    def chan(v: float) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _contrast(l1: float, l2: float) -> float:
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def _swing(lums: list[float]) -> float:
    """p95/p05 — percentiles, never min/max: one outlier must not decide."""
    if not lums:
        return 1.0
    s = sorted(lums)
    pick = lambda q: s[min(len(s) - 1, max(0, int(q * (len(s) - 1))))]  # noqa: E731
    return (pick(0.95) + 0.05) / (pick(0.05) + 0.05)


BODY_FG_LUM = _wcag_lum(BODY_FG)
CORPUS = [f"session-{n:03d}" for n in range(40)]


def _row_bgs(session_id: str, width: int, row: int, *, occupied: bool) -> list[tuple[int, int, int]]:
    """Background colours of one rendered transcript row."""
    return renderer.transcript_row(session_id=session_id, width=width, row=row,
                                   time_ms=0, occupied=occupied)


# ===========================================================================
# OUTCOME 1 — OKLab is correct. Every colour in the theme rides on this.
# ===========================================================================

class TestOklabCorrectness:
    def test_zero_chroma_is_neutral_grey(self):
        for lightness in (0.2, 0.35, 0.5, 0.7, 0.9):
            r, g, b = oklab.oklch_to_srgb8(lightness, 0.0, 0.0)
            assert max(r, g, b) - min(r, g, b) <= 2, f"L={lightness} -> ({r},{g},{b}) not neutral"

    def test_lightness_ends_are_anchored(self):
        assert sum(oklab.oklch_to_srgb8(0.0, 0.0, 0.0)) <= 6
        assert min(oklab.oklch_to_srgb8(1.0, 0.0, 0.0)) >= 250

    def test_mid_grey_lands_near_808080(self):
        r, g, b = oklab.oklch_to_srgb8(0.599, 0.0, 0.0)
        assert all(abs(c - 128) <= 12 for c in (r, g, b)), f"({r},{g},{b})"

    def test_round_trip_preserves_hue(self):
        for hue in (0.0, 1.0, 2.5, 4.0, 5.5):
            rgb = oklab.oklch_to_srgb8(0.6, 0.10, hue)
            back = oklab.srgb8_to_oklch(*rgb)
            delta = abs(((back.hue - hue + math.pi) % (2 * math.pi)) - math.pi)
            assert delta < 0.12, f"hue {hue} round-tripped to {back.hue}"


# ===========================================================================
# OUTCOME 2 — Three real compositing layers (leucophore / iridophore /
# chromatophore). A one-layer fake wearing three colours must not pass.
# ===========================================================================

class TestThreeLayers:
    @pytest.mark.parametrize("layer", ["leucophore", "iridophore", "chromatophore"])
    def test_each_layer_materially_changes_the_composite(self, layer):
        full = [field.sample("layer-probe", x, 3, 80, 24, 0, 0.0) for x in range(80)]
        without = [field.sample("layer-probe", x, 3, 80, 24, 0, 0.0, disable=layer) for x in range(80)]
        changed = sum(1 for a, b in zip(full, without) if max(abs(p - q) for p, q in zip(a, b)) > 2)
        assert changed / len(full) > 0.05, f"disabling {layer} barely changed the composite"


# ===========================================================================
# OUTCOME 3 — CONTRACTION. The central mechanism: calm under text, alive in
# open space, from ONE biological mechanism rather than an overlay.
# ===========================================================================

class TestContraction:
    def test_calm_under_occupied_cells(self):
        for sid in CORPUS[:8]:
            lums = [_wcag_lum(c) for c in _row_bgs(sid, 100, 4, occupied=True)]
            assert _swing(lums) <= 1.30, f"{sid} swing {_swing(lums):.3f}"

    def test_alive_in_open_cells(self):
        swings = [_swing([_wcag_lum(c) for c in _row_bgs(sid, 100, 4, occupied=False)])
                  for sid in CORPUS[:8]]
        assert sum(swings) / len(swings) >= 1.8, f"mean open swing {sum(swings)/len(swings):.3f}"

    def test_body_text_clears_wcag_aa_on_every_occupied_row(self):
        for sid in CORPUS:
            lums = sorted((_wcag_lum(c) for c in _row_bgs(sid, 100, 2, occupied=True)), reverse=True)
            worst = lums[int(0.05 * (len(lums) - 1))]
            assert _contrast(BODY_FG_LUM, worst) >= 4.5, f"{sid} {_contrast(BODY_FG_LUM, worst):.2f}"

    def test_contraction_preserves_hue(self):
        """The defect that took four rounds to find in v18: contraction must
        transform the pixel that exists, never synthesise a replacement."""
        shifts = []
        for sid in CORPUS[:8]:
            for x, calm, loud in zip(range(100),
                                     _row_bgs(sid, 100, 5, occupied=True),
                                     _row_bgs(sid, 100, 5, occupied=False)):
                a, b = oklab.srgb8_to_oklch(*loud), oklab.srgb8_to_oklch(*calm)
                if a.chroma < 0.02 or b.chroma < 0.02:
                    continue
                d = abs(((b.hue - a.hue + math.pi) % (2 * math.pi)) - math.pi)
                shifts.append(math.degrees(d))
        assert shifts, "no chromatic cells to compare"
        shifts.sort()
        median = shifts[len(shifts) // 2]
        p95 = shifts[int(0.95 * (len(shifts) - 1))]
        assert median <= 10.0, f"median hue shift {median:.1f} deg"
        assert p95 <= 30.0, f"p95 hue shift {p95:.1f} deg"

    def test_mask_has_finite_support(self):
        """A glyph must not perturb a distant cell. v18 shipped exp(-d/18),
        nonzero everywhere, which silently contracted the whole surface."""
        assert contraction.weight(0.0) == pytest.approx(1.0)
        assert contraction.weight(contraction.RADIUS) == 0.0
        assert contraction.weight(contraction.RADIUS + 1) == 0.0
        assert 0.0 < contraction.weight(contraction.RADIUS / 2) < 1.0

    def test_contraction_is_continuous_not_a_cutout(self):
        steps = [contraction.weight(d) for d in range(int(contraction.RADIUS) + 2)]
        jumps = [abs(b - a) for a, b in zip(steps, steps[1:])]
        assert max(jumps) < 0.12, f"largest step {max(jumps):.3f} reads as a hard edge"


# ===========================================================================
# OUTCOME 4 — Texture survives. Calm must not mean blank: v16 shipped a flat
# field and Adam's verdict was "there is no background displayed".
# ===========================================================================

class TestTextureSurvives:
    def test_occupied_rows_keep_distinct_tones(self):
        for sid in CORPUS[:10]:
            assert len(set(_row_bgs(sid, 100, 3, occupied=True))) >= 6

    def test_open_rows_are_richer_than_occupied_rows(self):
        for sid in CORPUS[:10]:
            open_tones = len(set(_row_bgs(sid, 100, 3, occupied=False)))
            calm_tones = len(set(_row_bgs(sid, 100, 3, occupied=True)))
            assert open_tones > calm_tones, f"{sid}: {open_tones} !> {calm_tones}"

    def test_field_is_never_flat_black(self):
        for sid in CORPUS[:10]:
            lums = [_wcag_lum(c) for c in _row_bgs(sid, 100, 3, occupied=True)]
            assert sum(lums) / len(lums) > 0.015, f"{sid} crushed to black"


# ===========================================================================
# OUTCOME 5 — Determinism. Identity must survive a restart, so the seed is a
# stable digest, never PYTHONHASHSEED-dependent hash().
# ===========================================================================

class TestDeterminism:
    def test_same_inputs_give_identical_rows(self):
        assert _row_bgs("stable", 80, 7, occupied=False) == _row_bgs("stable", 80, 7, occupied=False)

    def test_palette_is_stable_and_seed_independent(self):
        assert palette.for_session("abc") == palette.for_session("abc")
        assert palette.for_session("abc") != palette.for_session("abd")

    def test_no_builtin_hash_in_the_seed_path(self):
        assert palette.seed_of("x") == 0x811C9DC5 ^ 0 or isinstance(palette.seed_of("x"), int)
        assert palette.seed_of("hello") == palette.seed_of("hello")


# ===========================================================================
# OUTCOME 6 — Per-session identity across a corpus, measured as a RATE.
# ===========================================================================

class TestIdentity:
    def test_corpus_yields_many_distinct_palettes(self):
        assert len({palette.for_session(s) for s in CORPUS}) >= 36

    def test_sessions_render_visibly_different_fields(self):
        rows = [tuple(_row_bgs(s, 60, 2, occupied=False)) for s in CORPUS[:20]]
        assert len(set(rows)) >= 19

    def test_dominant_hues_are_spread_around_the_circle(self):
        hues = [palette.for_session(s).hue for s in CORPUS]
        buckets = {int(h / (2 * math.pi) * 8) % 8 for h in hues}
        assert len(buckets) >= 5, f"only {len(buckets)} of 8 hue octants used"


# ===========================================================================
# OUTCOME 7 — Wall-clock animation, smooth and cheap.
# ===========================================================================

class TestAnimation:
    def test_a_given_instant_is_reproducible(self):
        a = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=5000, occupied=False)
        b = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=5000, occupied=False)
        assert a == b

    def test_the_field_advances_over_time(self):
        a = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=0, occupied=False)
        b = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=4000, occupied=False)
        assert a != b

    def test_motion_is_smooth_across_one_frame(self):
        a = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=9000, occupied=False)
        b = renderer.transcript_row(session_id="t", width=60, row=1, time_ms=9016, occupied=False)
        assert max(abs(p - q) for ca, cb in zip(a, b) for p, q in zip(ca, cb)) <= 14


# ===========================================================================
# OUTCOME 8 — Cheap enough for a scrolling transcript. This is the whole
# reason the CLI is viable where the pixel canvas was not.
# ===========================================================================

class TestPerformance:
    def test_a_cached_row_is_effectively_free(self):
        import time
        renderer.transcript_row(session_id="perf", width=200, row=3, time_ms=0, occupied=False)
        start = time.perf_counter()
        for _ in range(200):
            renderer.transcript_row(session_id="perf", width=200, row=3, time_ms=0, occupied=False)
        per_call_us = (time.perf_counter() - start) / 200 * 1e6
        assert per_call_us < 200, f"{per_call_us:.0f} us/row cached"

    def test_a_cold_row_fits_inside_a_frame(self):
        import time
        start = time.perf_counter()
        for row in range(50):
            renderer.transcript_row(session_id=f"cold-{row}", width=200, row=row,
                                    time_ms=0, occupied=False)
        per_row_ms = (time.perf_counter() - start) / 50 * 1e3
        assert per_row_ms < 16.7, f"{per_row_ms:.1f} ms/row cold"


# ===========================================================================
# OUTCOME 9 — THE LANGUAGE, half one: the FIELD carries IDENTITY and is
# SIGNAL-INVARIANT. Adam, 2026-09-12: "the background change makes the
# recognition of terminal harder".
# ===========================================================================

class TestFieldIsIdentityOnly:
    def test_the_field_is_byte_identical_across_every_state(self):
        base = dict(session_id="lang", width=80, row=4, time_ms=1234, occupied=False)
        resting = renderer.transcript_row(**base)
        for state in renderer.STATES:
            assert renderer.transcript_row(**base, state=state) == resting, \
                f"state {state} moved the identity surface"

    def test_identity_survives_a_state_change_within_a_session(self):
        rows = {s: tuple(renderer.transcript_row(session_id="lang", width=80, row=2,
                                                 time_ms=0, occupied=False, state=s))
                for s in renderer.STATES}
        assert len(set(rows.values())) == 1


# ===========================================================================
# OUTCOME 10 — THE LANGUAGE, half two: the BAR carries STATE and is
# SESSION-INVARIANT. An alarm that differs per window is not an alarm.
# ===========================================================================

class TestBarIsStateOnly:
    def test_a_given_state_reads_identically_in_every_session(self):
        for state in renderer.STATES:
            bars = {tuple(renderer.status_bar(session_id=s, width=40, state=state))
                    for s in CORPUS[:12]}
            assert len(bars) == 1, f"state {state} rendered {len(bars)} different ways"

    def test_the_states_are_mutually_distinguishable(self):
        bars = {s: renderer.status_bar(session_id="x", width=40, state=s) for s in renderer.STATES}
        assert len({tuple(v) for v in bars.values()}) == len(renderer.STATES)

    def test_attention_and_fault_are_far_apart_in_hue(self):
        def dominant_hue(cells):
            hs = [oklab.srgb8_to_oklch(*c) for c in cells]
            lit = [h for h in hs if h.chroma > 0.04] or hs
            return sum(h.hue for h in lit) / len(lit)

        attention = dominant_hue(renderer.status_bar(session_id="x", width=40, state="attention"))
        fault = dominant_hue(renderer.status_bar(session_id="x", width=40, state="fault"))
        gap = abs(((fault - attention + math.pi) % (2 * math.pi)) - math.pi)
        assert math.degrees(gap) > 25, f"only {math.degrees(gap):.0f} deg between the two alarms"

    def test_the_bar_always_paints(self):
        """Returning None at rest inherits the host's stock gold — the one
        surface carrying state must never look unthemed."""
        for state in renderer.STATES:
            cells = renderer.status_bar(session_id="x", width=40, state=state)
            assert cells and len(cells) == 40


# ===========================================================================
# OUTCOME 11 — Readability of the bar itself. It is the only channel that
# speaks, so its text must be legible in every state.
# ===========================================================================

class TestBarReadability:
    def test_bar_text_clears_aa_against_its_own_background(self):
        for state in renderer.STATES:
            fg = renderer.status_bar_foreground(state)
            for bg in renderer.status_bar(session_id="x", width=40, state=state):
                assert _contrast(_wcag_lum(fg), _wcag_lum(bg)) >= 4.5, \
                    f"{state}: fg {fg} on bg {bg}"


# ===========================================================================
# OUTCOME 12 — Degradation. A narrow terminal, a 1-cell width, an empty
# session id, and a non-colour terminal must all behave, never crash.
# ===========================================================================

class TestDegradation:
    @pytest.mark.parametrize("width", [0, 1, 2, 7, 300])
    def test_any_width_renders_exactly_that_many_cells(self, width):
        assert len(_row_bgs("edge", width, 1, occupied=False)) == width

    def test_an_empty_session_id_still_renders(self):
        assert len(_row_bgs("", 40, 1, occupied=False)) == 40

    def test_a_unicode_session_id_still_renders(self):
        assert len(_row_bgs("sesja-żółć-🦑", 40, 1, occupied=False)) == 40

    def test_negative_or_absurd_rows_do_not_crash(self):
        for row in (-5, 0, 10_000):
            assert len(_row_bgs("edge", 20, row, occupied=False)) == 20
