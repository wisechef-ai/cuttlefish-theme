"""Rich-safe input-rule chromatophores driven by the body-pattern field.

WHY THIS IS TEXT: a plugin cannot paint arbitrary terminal pixels through semantic
skin keys. Rich markup is ours to emit, so each cell can carry one measured pigment.
The rule therefore samples the same coherent, seeded body grammar as the mantle
instead of cycling a palette by x-coordinate (the old output was terminal tinsel).
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache

from .band import _FAMILY_ARC, reserved_for_alarm
from .color.identity import allocate
from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from .pattern import render
from .patterns import field_for

# Share of columns carrying a dot. The reference renders measure 5-25% lit
# (docs/reference-structure.md), against the 0.30 this surface used before.
#
# NOTE THE QUANTISATION: cells() spends this budget per 10-column SEGMENT, as
# `round(_VIVID_FRACTION * 10)`, so the knob only moves in steps of 0.1 and
# 0.15/0.20/0.25 all render identically at 2 dots per 10 columns. 0.20 is
# written here because it is what the surface actually paints; the other two
# values would be a comment that disagrees with the screen.
#
# It costs identity, measured and accepted: sparser dots mean fewer distinct
# quantised dot-sets, so rendered rule signatures over 200 sessions fall from
# 64 (at 0.30) to 39. Adam chose reference-accurate sparsity on 2026-09-13.
_VIVID_FRACTION = 0.20

# A bar is a LIT strip, not a background behind text, so it ramps bright. These
# are the bands the pre-v11 bars used; only the hue source changed.
_BAR_L = (0.66, 0.84)
_ACUTE_BAR_L = (0.62, 0.78)


def _identity_variants(session_id: str) -> tuple[str, ...]:
    """The bars' ramp, drawn from the SAME palette the mantle paints.

    Adam, 2026-09-11: "there should be a general colour palette per session and
    this should reflect that." Both surfaces read `mantle_palette._mantle_classes`, so a
    bar colour is always a mantle colour. Sourcing them separately is what made
    koralen's bar sit at hues 180/210/330 while its mantle sat at 30/270/300/360
    — one session wearing two unrelated skins.

    The bar re-spreads those hues across its own lightness range: the mantle sits
    BEHIND TEXT and must stay dark, a bar is a lit strip and should read bright.

    A colour inside the alarm arc is pushed to the arc's NEAREST EDGE, not
    rotated 180 degrees. Rotation was the old fix and it cost more than it
    bought: a mantle red at hue 354 became a bar CYAN at 174, so the bar left
    its own session's hue family entirely. Measured 2026-09-12, that fired on
    9 of 12 sessions — the single largest source of "the bar doesn't match".
    Displacing to the edge keeps the colour adjacent to where it started, which
    is all the alarm separation needs.
    """
    from .mantle_palette import _mantle_classes
    from .color.oklab import hex_to_oklch
    palette = [hex_to_oklch(colour) for colour in _mantle_classes(session_id, "resting")]
    # Alarm-hued islands are DROPPED here, not displaced. The mantle may carry a
    # red fleck — it is one dark cell among many and reads as a marking. The bar
    # is a LIT strip at L .50-.80, where the same hue reads as the alarm itself,
    # so `test_resting_bars_never_wear_the_alarm_colours` is right to refuse it.
    # Displacing instead of dropping was tried: it moves the colour off its own
    # family and puts the bar back out of step with the mantle.
    calm = [c for c in palette if not reserved_for_alarm(c.h)]
    return _ramp(calm or palette, _BAR_L)


def _ramp(colours, lightness: tuple[float, float]) -> tuple[str, ...]:
    """16 steps across `colours` (OKLCh), darkest to brightest.

    Lightness is re-spread across `lightness` while each step keeps ITS OWN
    hue and chroma. The two surfaces share a palette but not a brightness: the
    mantle sits BEHIND TEXT and must stay dark, whereas a bar is a lit strip and
    should read bright.

    Hue is NOT interpolated between colours. Blending a violet into an amber
    walks the whole colour circle and lands the resting bar on the alarm hues —
    measured, a resting bar hit 14 distinct hues and collided with the amber
    alarm on half its palette. The animal shows its classes side by side; it does
    not cross-fade them.

    Steps are allocated by the palette's own DOMINANCE, not one slice each. An
    even split hands a single island colour 4 of 16 cells — 25% of the bar to a
    colour the mantle spends ~18% of its cells on — and that is what left six
    sessions' bars reading as a different hue family from their own mantle.
    """
    ordered = sorted(colours, key=lambda c: c.L)
    floor, ceiling = lightness
    weights = Counter(int(c.h // _FAMILY_ARC) for c in ordered)
    # Cumulative share of the strip each colour owns, in palette order.
    total = sum(weights[int(c.h // _FAMILY_ARC)] for c in ordered)
    bounds, running = [], 0.0
    for colour in ordered:
        running += weights[int(colour.h // _FAMILY_ARC)] / total
        bounds.append(running)
    steps = []
    for index in range(16):
        fraction = index / 15
        source = next((c for c, edge in zip(ordered, bounds) if fraction <= edge),
                      ordered[-1])
        steps.append(oklch_to_hex(source.with_(L=floor + (ceiling - floor) * fraction)))
    return tuple(steps)


def _oklch_variants(base: OKLCh) -> tuple[str, ...]:
    return tuple(oklch_to_hex(base.with_(L=0.50 + 0.30 * fraction))
                 for fraction in (i / 15 for i in range(16)))


def _acute_variants(signal: str) -> tuple[str, ...]:
    """The bars under an acute signal — the SAME fixed classes the mantle uses.

    Sharing `chromatophore_set` means the bars and the background change together
    and change hard: a session's own hues vanish and the fixed amber or red takes
    the whole surface, identically in every terminal.

    The cool iridophore and the pale leucophore are both dropped here. On the
    mantle they are the backdrop the pigments sit above, but a one-row bar has no
    room for a backdrop: ramping through the iridophore dragged the amber alarm
    to hue 205 (teal), and the leucophore is a near-grey pearl (C 0.03) whose
    ends quantise to C 0.000 — a grey bar where an alarm should be. `family` is
    exactly the channel naming which classes carry the state, so the bar keeps
    only those and ramps lightness across them.
    """
    from .mantle import chromatophore_set
    from .session import Signal
    collapsed = Signal.FAULT if signal in ("fault", "error") else Signal.NEEDS_ME
    classes = chromatophore_set(allocate("acute"), collapsed)
    return _ramp([c.oklch for c in classes if c.family in ("amber", "red")], _ACUTE_BAR_L)


def _signal_time(signal: str) -> float:
    if signal in ("needs-me", "needs_me"):
        return 0.35
    if signal in ("fault", "error"):
        return 0.70
    return 0.0


@lru_cache(maxsize=32)
def _body_field(session_id: str, signal: str, width: int, height: int):
    """The session's body patch, built once and shared by every row.

    Building a 64-row field costs ~45ms; the transcript asks for one row per
    printed line, so rebuilding per row_key put that on every line of output.
    """
    return field_for(session_id, width, height, t=_signal_time(signal))[1]


@lru_cache(maxsize=64)
def _unlit(session_id: str, signal: str) -> str:
    """The single flat colour every unlit cell of the rule wears.

    Adam, 2026-09-13: "can we have a thin line in one color - in that case would
    be that blue and the dots as it is now scattered on that (without this
    background)". So: ONE colour under the whole rule, dots on top of it, and no
    second tone anywhere for the eye to read as a gap.

    HUE COMES FROM THE SHARED ANCHOR, LIGHTNESS IS THIS SURFACE'S OWN. That split
    is the whole subtlety (§6g of the authoring skill). Deriving the ground from
    `allocate()` directly — the obvious move, and one that passes every test
    looking at this surface alone — gives the rule a hue nothing else on screen
    is using: measured, cross-surface hue agreement fell from 20/20 sessions to
    4/20, i.e. most windows wore a palette in one family and a rule in another.
    `_mantle_palette` is the band-derived anchor every other surface reads, so
    taking the hue from there keeps one theme per window.

    Only the LIGHTNESS is re-derived here, because a rule is a lit strip rather
    than a background behind text and the band's own floor is darker than this
    surface wants.
    """
    from .mantle_palette import _mantle_palette
    from .color.terminal import _index_to_hex, quantize_cube_256
    from .session import Signal
    # `cells` takes wire-form signals ("needs-me"/"error"); Signal's values are
    # canonical ("needs_me"/"fault"). Passing the wire form straight through
    # raises ValueError inside a repaint, which the renderer swallows as None —
    # the bar silently reverts to stock on exactly the states that matter.
    canonical = (Signal.FAULT if signal in ("fault", "error") else
                 Signal.NEEDS_ME if signal in ("needs-me", "needs_me") else Signal.RESTING)
    anchor = hex_to_oklch(_mantle_palette(session_id, canonical.value))
    # Walk DOWN from the top of the window: the quantised value is the contract
    # the user actually sees, and the cube is sparse enough in this region that a
    # high-chroma hue can land above where it was aimed.
    for lightness in (0.28 - 0.01 * step for step in range(10)):
        ground = oklch_to_hex(anchor.with_(L=lightness))
        if 0.20 <= hex_to_oklch(_index_to_hex(quantize_cube_256(ground))).L <= 0.34:
            return ground
    return oklch_to_hex(anchor.with_(L=0.20))


@lru_cache(maxsize=512)
def cells(session_id: str, signal: str, width: int,
          row_key: int | None = None) -> tuple[tuple[str, str, str], ...]:
    """(fg, bg, glyph) per column — the one source every formatter renders from.

    ``row_key`` selects a stable body-field row for transcript painting.  The
    default keeps the original one-row projection used by the input rule.
    """
    width = max(0, int(width))
    if not width:
        return ()

    # A one-cell-high rule is a projection of a small body patch: take the local
    # maximum, then pick by rank per 10-column segment. Rank (not an absolute
    # threshold) gives every seed the same budget, including degenerate fields.
    # Segments (not a global top-N) stop the 2D field's clustering from leaving
    # voids — globally it lit 3 clumps around a 33-cell dead gap.
    field = _body_field(session_id, signal, width, 64 if row_key is not None else 3)
    if row_key is None:
        values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    else:
        values = [field.get(x, int(row_key) % field.height) for x in range(width)]
    hottest = lambda columns, n: sorted(columns, key=lambda x: (values[x], x), reverse=True)[:n]
    segment = 10
    vivid = {x for start in range(0, width, segment)
             for x in hottest(range(start, min(width, start + segment)),
                              max(1, round(_VIVID_FRACTION * segment)))}

    ground = _unlit(session_id, signal)
    variants = (_acute_variants(signal) if signal in ("fault", "error", "needs-me", "needs_me")
                else _identity_variants(session_id))
    rank = {x: i for i, x in enumerate(hottest(vivid, len(vivid)))}
    out: list[tuple[str, str, str]] = []
    for x, value in enumerate(values):
        if x not in vivid:
            out.append((ground, ground, "─"))
        else:
            # Brightest cell gets the palest pigment — retracted skin reveals
            # the layer beneath, it does not simply go dark.
            step = int((rank[x] + 1) * len(variants) / len(vivid))
            out.append((variants[min(len(variants) - 1, step)], ground,
                        "━" if value >= 0.70 else "─"))
    return tuple(out)


def separator_markup(session_id: str, signal: str, width: int) -> str:
    return "".join(f"[{fg} on {bg}]{glyph}[/]"
                   for fg, bg, glyph in cells(session_id, signal, width))


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["cells", "separator", "separator_markup"]
