"""Prompt-toolkit chrome rendering for the persistent input rule."""
from __future__ import annotations

from functools import lru_cache
from hashlib import blake2b
from math import gcd
from typing import Any

from .color.identity import allocate
from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from .color.terminal import _index_to_hex, contrast_ratio, quantize_256, quantize_cube_256
from .linework import cells
from .pattern import ACUTE_AMBER, ACUTE_FAULT
from .session import Signal, collapse

# Anything painted BEHIND TEXT must clear WCAG AA against the body foreground.
# A lightness ceiling only approximates this: at L .52 a dark red clears 4.6:1
# while an equally light green reaches 4.1:1, so the ratio is measured instead.
_BODY_FOREGROUND = "#E8E6EA"
_AA_RATIO = 4.5
_DARKENING_STEPS = (0.52, 0.46, 0.40, 0.34, 0.28, 0.22)

# The acute status bar is a LOUD surface, not a background: it should catch the
# eye across a room. Adam, 2026-09-11: "the bars should be bright and the text is
# white." Pure white on a bright bar is not reachable at AA — #FFAF00 carries
# white at only 1.84:1 — so the bar sits at the brightest cube entry that still
# holds white text: measured 4.71:1 (amber) and 5.40:1 (red).
_ACUTE_BAR_L = 0.57
_ACUTE_BAR_FOREGROUND = "#FFFFFF"

# (lightness delta, hue delta) tried in order when two classes quantise onto one
# cube entry. Lightness first — it separates without changing what the class IS.
# How many island colours join the dominant family. Two is enough to read as
# variation without becoming a second dominant; the target share is 8-20%.
_ISLAND_COLOURS = 2

# Four distinct colours per session, the contract that predates v13: fewer and
# two sessions start reading alike.
_MIN_PALETTE = 4

# How far a shade may be pulled toward a neighbouring colour. A quarter-step
# reaches a fresh cube index while the hue still reads as the family's own.
_TINT = 0.25

# Share of LIT cells the islands take: the hottest tail of the ramp. The
# contract wants a 0.75-0.92 dominant share, so islands stay a minority marking.
_ISLAND_SHARE = 0.15

_SEPARATION_NUDGES = ((0.08, 0), (-0.08, 0), (0.16, 0), (-0.16, 0),
                      (0.0, 25), (0.0, -25), (0.24, 0), (0.0, 50))


@lru_cache(maxsize=32)
def _mantle_palette(session_id: str) -> str:
    """The ground the session's transcript mantle is painted on.

    The ground is the DARKEST STEP OF THE SESSION'S OWN BAND, not a separate
    near-black. Measured, the band alone spans a 1.42x contrast swing, but the
    old #0B0C10 ground dragged it to 1.96x: a line of text crossing both fell
    into a hole, the eye adapted to the lit cells and lost the glyphs over the
    dark ones. That hole is what "the text now is not visible good" was.

    Cached because this is a session constant asked for once per printed line.
    """
    return _dominant_palette(session_id)[0]


@lru_cache(maxsize=64)
def _mantle_classes(session_id: str, signal: str) -> tuple[str, ...]:
    """The session's chromatophore classes, quantised, darkest first.

    Four classes, not one colour: two dark pigments from different hue families,
    the cool iridophore complement, and the sparse bright leucophore. Under an
    acute signal `chromatophore_set` returns the FIXED amber/red sets instead,
    so "that terminal needs me" reads the same across every session.

    In the animal the iridophore and leucophore are the BACKDROP the pigments sit
    above; here they sit BEHIND TEXT, so every class is darkened until it clears
    WCAG AA against the body foreground. Lightness alone is the wrong guard: a
    saturated green at L .52 still reaches only 4.1:1, so the contract is
    measured directly rather than approximated. Hue and ordering survive.

    Classes are then separated: the cube is sparse down here, so 77 of 1000
    sessions had two classes quantise onto one entry (s10 rendered three colours
    where four were designed). A collapsed class is a session that looks like
    another session, which is the identity the mantle exists to carry.
    """
    from .mantle import chromatophore_set
    classes = chromatophore_set(allocate(session_id), Signal(signal))
    if Signal(signal) is Signal.RESTING:
        return _dominant_palette(session_id)
    return _distinct(tuple(c.oklch for c in classes))


@lru_cache(maxsize=8)
def _shades_of(family: tuple[str, ...]) -> tuple[str, ...]:
    """The family's real colours plus the dithered tones between its endpoints.

    The dark cube is sparse: the band's smallest hue family holds two entries,
    which is not enough for two sessions drawing from it to look different.
    `dither` manufactures the tones in between, so a 2-shade family becomes 5.

    Shades that quantise onto an index already taken are dropped. A blend the
    terminal cannot distinguish is not a shade — #690000 and #7D0000 are two
    colours in OKLab and one colour on screen, and keeping both let two sessions
    build "different" palettes that rendered identically.
    """
    from .band import band, family_of
    from .dither import perceived
    ordered = sorted(family, key=lambda c: hex_to_oklch(c).L)
    # Blend within the family AND a little way toward every other band colour.
    # Within-family blends alone are not enough: the red family holds two cube
    # entries and every mix of them quantises back onto those two, so two
    # sessions drawing red had no third shade to differ by. A quarter-step
    # toward a neighbour reaches a new index while the hue still reads as red.
    steps = [perceived(lower, upper, quarter / 4)
             for lower, upper in zip(ordered, ordered[1:])
             for quarter in range(5)]
    steps += [perceived(member, other, _TINT)
              for member in ordered for other in band() if other not in family]
    seen: dict[int, str] = {}
    for colour in sorted(set(ordered) | set(steps), key=lambda c: hex_to_oklch(c).L):
        if family_of(colour) == family_of(ordered[0]):
            seen.setdefault(quantize_256(colour), colour)
    return tuple(seen.values())


def _coprime_stride(count: int, seed: int) -> int:
    """A stride that visits every slot of a `count`-long ring before repeating.

    Sharing a factor with `count` makes the walk revisit slots, which silently
    shrinks a palette — 5 of 200 sessions lost a colour that way.
    """
    candidates = [step for step in range(1, max(2, count)) if gcd(step, count) == 1]
    return candidates[seed % len(candidates)] if candidates else 1


def _dominant_palette(session_id: str) -> tuple[str, ...]:
    """One hue family carrying the pattern, plus a few island colours.

    Adam, 2026-09-11: "one dominant with just small islands of other colors".
    Measured, the even four-class mix scored 0.367 dominant share against a
    0.75-0.92 target and read as confetti rather than skin.

    Every colour comes from `band`, so the whole palette sits inside one narrow
    lightness range and a line of text crosses a near-uniform background. That
    is the legibility half; `dither` supplies the tones the narrow band cannot.

    A session varies WHICH SHADES of its dominant family it wears, not just
    which family. Taking the whole family gave 30 constructible palettes, so 200
    sessions could not look different from one another; choosing a subset gives
    191 while keeping every colour in one hue.
    """
    from .band import families
    groups = families()
    seed = int.from_bytes(blake2b(session_id.encode(), digest_size=4).digest(), "big")
    family = groups[seed % len(groups)]
    others = [colour for index, group in enumerate(groups)
              if index != seed % len(groups) for colour in group]
    # The dominant family is DITHER-EXPANDED before a session draws from it. Two
    # sessions on the two-shade red family had nothing to tell them apart and
    # produced identical palettes (tori-main and tilola did); blending the
    # family's own endpoints turns 2 real shades into 5 usable ones, all inside
    # the band and all the same hue.
    shades = _shades_of(family)
    # A session must still show four distinct colours — that contract predates
    # v13 and is what stops two sessions reading alike — so the dominant family
    # keeps at least two shades and the islands make the rest up.
    keep = min(len(shades), 2 + (seed >> 4) % max(1, len(shades) - 1))
    start = (seed >> 12) % len(shades)
    # The dominant walk strides too, for the same reason the island walk does:
    # with a fixed stride, two sessions that draw the same COUNT from the same
    # family pick the same shades (tori-main and tilola both took two reds). The
    # stride is kept coprime with the shade count so the walk visits `keep`
    # DISTINCT shades — a common factor revisits one and the palette shrinks.
    step_by = _coprime_stride(len(shades), seed >> 28)
    dominant = tuple(shades[(start + step * step_by) % len(shades)] for step in range(keep))
    count = max(_MIN_PALETTE - len(dominant), 1 + (seed >> 20) % _ISLAND_COLOURS)
    # Stride the island walk as well as its offset: with a fixed stride two
    # sessions sharing a dominant family and island count landed on identical
    # palettes (tilola and chef did).
    stride = 1 + (seed >> 24) % max(1, len(others) - 1) if others else 1
    offset = (seed >> 8) % len(others) if others else 0
    islands = tuple(others[(offset + step * stride) % len(others)]
                    for step in range(min(count, len(others))))
    return tuple(sorted(set(dominant + islands), key=lambda c: hex_to_oklch(c).L))


def _distinct(colours: tuple[OKLCh, ...]) -> tuple[str, ...]:
    """Quantise `colours`, nudging any that land on an already-used cube entry.

    Lightness moves first and hue only as a fallback, because a class is defined
    by its hue family: shifting L keeps "the dark red one" dark red, while
    shifting h turns it into a different class entirely.
    """
    taken: list[str] = []
    for colour in colours:
        candidate = _readable(colour)
        for nudge in _SEPARATION_NUDGES:
            if candidate not in taken:
                break
            candidate = _readable(colour.with_(L=max(0.12, colour.L + nudge[0]),
                                               h=(colour.h + nudge[1]) % 360))
        taken.append(candidate)
    return tuple(taken)


def _readable(colour: OKLCh, foreground: str = _BODY_FOREGROUND) -> str:
    """Darken `colour` until `foreground` clears AA on top of it.

    Quantisation happens first: AA has to hold for the hex the TERMINAL is sent,
    not the one we asked for. The foreground is a parameter because the status
    bar pairs a bright background with white text, where the body's near-white
    would give a different answer.
    """
    for lightness in (colour.L, *_DARKENING_STEPS):
        if lightness > colour.L:
            continue
        candidate = _index_to_hex(quantize_cube_256(oklch_to_hex(colour.with_(L=lightness))))
        if contrast_ratio(foreground, candidate) >= _AA_RATIO:
            return candidate
    return _index_to_hex(quantize_cube_256(oklch_to_hex(colour.with_(L=_DARKENING_STEPS[-1]))))


@lru_cache(maxsize=512)
def _mantle_row(session_id: str, width: int, row_key: int,
                signal: str = Signal.RESTING.value) -> tuple[tuple[str, str], ...]:
    """One row of the transcript mantle, as prompt_toolkit fragments.

    WHICH class shows at a cell follows that cell's own pigment, which `cells`
    already assigns by field intensity — deeper classes for stronger expansion,
    as the animal recruits them. Never by column index: that is the alternating
    stripe v7 removed.

    Cached whole: this is called once per printed line, and rebuilding an
    80-element list of f-strings per line is most of the cost at that rate.
    """
    ground = _mantle_palette(session_id)
    classes = _mantle_classes(session_id, signal)
    row = cells(session_id, signal, width, row_key)
    # `cells` marks unlit cells with ITS ground, which is not ours: v13 moved the
    # mantle ground into the session's band. Comparing against the wrong one made
    # every cell read as lit and the mantle lost its ground entirely (measured:
    # 200/200 cells pigment). Take the unlit marker from the row itself.
    unlit = row[0][1]
    ramp = sorted({fg for fg, _bg, _g in row if fg != unlit},
                  key=lambda pigment: hex_to_oklch(pigment).L)
    # Reserve the islands for the hottest CELLS, not the hottest ramp positions.
    # The ramp holds only a handful of distinct values, so a top-slice of its
    # positions caught 38% of cells where 15% was asked for — the confetti Adam
    # saw. Counting cells makes the share mean what it says.
    dominant, islands = _split(session_id, classes)
    order = {pigment: rank for rank, pigment in enumerate(ramp)}
    hottest = sorted((fg for fg, _bg, _g in row if fg != unlit),
                     key=lambda pigment: hex_to_oklch(pigment).L, reverse=True)
    island_cells = set(hottest[:round(_ISLAND_SHARE * len(hottest))]) if islands else set()
    shade = {pigment: islands[rank % len(islands)] if pigment in island_cells
             else dominant[min(len(dominant) - 1, int(rank / max(1, len(ramp) - 1) * len(dominant)))]
             for pigment, rank in order.items()}
    return tuple((f"bg:{ground if fg == unlit else shade[fg]}", " ")
                 for fg, _bg, _glyph in row)


def _split(session_id: str, classes: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate a palette into its dominant family and its islands.

    The ground is excluded from both: it is the palette's darkest step, so a lit
    cell painted with it is invisible against the unlit ones. Leaving it in the
    dominant ramp dropped measured pigment density to 15%.
    """
    from .band import family_of
    ground = _mantle_palette(session_id)
    paints = tuple(c for c in classes if c != ground) or classes
    if len(paints) < 2:
        return paints, ()
    home = family_of(ground)
    dominant = tuple(c for c in paints if family_of(c) == home)
    islands = tuple(c for c in paints if family_of(c) != home)
    return (dominant or paints), islands


def _acute_status_bar(signal: Signal) -> tuple[str, str]:
    """The acute bar's background AND the foreground that stays legible on it.

    The bar is painted over fragments carrying their own colours — silver, gold,
    olive-grey — and prompt_toolkit lets the last style win, so the plugin must
    supply both halves of the pair. Supplying only a background left the default
    #C0C0C0 text at 1.01:1 on quantised amber: the status bar went blank exactly
    when it had something to say.

    No cube colour clears AA against all six stock status-bar foregrounds at once
    (#8B8682 sits mid-range and collides with everything), so the plugin pins its
    own pair: the brightest cube entry that still carries WHITE text.
    """
    oklch = ACUTE_FAULT if signal is Signal.FAULT else ACUTE_AMBER
    background = _readable(oklch.with_(L=_ACUTE_BAR_L), _ACUTE_BAR_FOREGROUND)
    return background, _ACUTE_BAR_FOREGROUND


def chrome_renderer(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render persistent chrome, failing closed on any repaint-path problem."""
    try:
        signal = collapse(ctx.get("pet_state"))
        if surface == "status_bar_bg":
            if signal is Signal.RESTING:
                return None
            colour, foreground = _acute_status_bar(signal)
            # Fill the bar: the core pads a short list with the EMPTY style, so
            # one cell would leave the rest stock — an alarm you cannot see.
            return [(f"bg:{colour} {foreground}", " " * max(0, int(width)))]
        session_id = ctx.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return None
        if surface == "transcript_line":
            row_key = ctx.get("row_key")
            row_key = int(row_key) if isinstance(row_key, int) and not isinstance(row_key, bool) else 0
            return list(_mantle_row(session_id, int(width), row_key, signal.value))
        if surface not in {"input_rule_top", "input_rule_bot"}:
            return None
        return [(f"fg:{fg} bg:{bg}", glyph)
                for fg, bg, glyph in cells(session_id, signal.value, int(width))]
    except Exception:
        return None


__all__ = ["chrome_renderer"]
