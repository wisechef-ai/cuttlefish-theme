"""Cell-resolution three-layer cuttlefish skin field."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from . import contraction, noise, oklab, palette

# The reference structure measures most of the frame at OKLab L .05-.10 — a
# dark window carrying sparse pigment. The leucophore is the PALE layer that
# contraction reveals, not a base coat: at L .25 / alpha .88 it lifted the
# darkest cell of a 200-cell row to L .138 (median .243), so every cell read
# as lit and the field became a panel laid over the terminal.
LEUCOPHORE_LIGHTNESS = 0.09
IRIDOPHORE_LIGHTNESS = 0.05
# WHY 0.22: this is the floor for a cell that selection has already decided to
# light, so it must be VISIBLY pigmented — being spared the ground-snap is not
# the same as being seen. At the old 0.025 a winner in a low-texture cell
# composited to (0,1,1): lit by construction, invisible on screen. Measured
# across 8 sessions x 5 rows, winners landing below the snap luma (sum rgb <= 28)
# went 102 -> 52 (0.10) -> 7 (0.16) -> 0 (0.22). 0.28 also gives 0 and costs
# contrast headroom for no gain, so 0.22 is the smallest value that makes every
# selected cell actually appear.
PIGMENT_BASE_LIGHTNESS = 0.22
# WHY: bounded chroma keeps the sparse pigment colourful without glare.
LEUCOPHORE_CHROMA = 0.055
IRIDOPHORE_CHROMA = 0.05
PIGMENT_CHROMA = 0.08
# WHY: compositing ceilings preserve distinct layers while avoiding whiteout.
# Leucophore alpha. This layer is the PALE one, and painting it everywhere at
# high alpha lifts the whole frame off the window: measured at 0.88 the darkest
# cell in a 200-cell row was OKLab L 0.138 with a median of 0.243, against a
# reference structure that wants most of the frame at L .05-.10. It is a
# BACKDROP revealed by contraction, not a base coat.
LEUCOPHORE_ALPHA = 0.55
IRIDOPHORE_ALPHA = 0.45
PIGMENT_ALPHA_CEILING = 0.76

# Pigment is selected as the top-k cells WITHIN each fixed segment, which
# fixes density at k/segment by construction and bounds the dark gap. The
# reference structure measures 5-25% of the frame lit; 1-in-5 lands at 20%.
PIGMENT_SEGMENT_WIDTH = 5
PIGMENT_TOP_K = 1
NOISE_TIME_SCALE = 0.000018

# The colour the theme sets as the terminal's OSC-11 background. Cells with no
# pigment MUST land here exactly: a field whose unlit ground differs from the
# window behind it reads as a lighter PANEL laid on the terminal, with visible
# edges wherever painting stops. Measured before this was pinned: per-session
# grounds of #050a09 / #05090e against a #0B0C10 window.
TERMINAL_GROUND = (0x0B, 0x0C, 0x10)

# Below this summed 8-bit channel value a cell carries no visible pigment and is
# snapped to the window colour rather than left a near-miss. 66 is the sum that
# matches the OKLab L .11 this was originally expressed as, measured against the
# composited field; a sum is ~20x cheaper and this runs once per cell.
GROUND_SNAP_LUMA = 28
# WHY: the contraction mask is radial; its centre is full weight by definition.
MASK_CENTRE = 0.0

# The lightness a fully contracted cell settles toward, and how much of its own
# lightness it keeps on the way. Quantising into CALM_STEPS levels is what makes
# text-row tones COLLAPSE rather than merely shift: measured, an unquantised
# contraction left 28 tones under text against 16 in the open field.
CALM_LIGHTNESS = 0.36
CALM_LIGHTNESS_RETENTION = 0.05
CALM_STEPS = 24

# Chroma a contracted cell may keep: a floor so it stays chromatic (a greyscale
# calm band reads as a scrim) plus a small per-cell range. The RANGE is what
# lets each cell keep its own colour, so it is the knob that decides whether a
# text row stays busier than an open one — measured over 12 sessions, range
# .035 left open richer in only 10, .012 in 11 while keeping 18 tones.
CALM_CHROMA_FLOOR = 0.028
CALM_CHROMA_RANGE = 0.012


@dataclass(frozen=True)
class _SampleRequest:
    """Coordinates and identity inputs for one field cell."""

    session_id: str
    x: int
    y: int
    width: int
    height: int
    row: int
    time_ms: float


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Blend two RGB colours by a clamped alpha."""
    alpha = max(0.0, min(1.0, alpha))
    return (round(a[0] + (b[0] - a[0]) * alpha),
            round(a[1] + (b[1] - a[1]) * alpha),
            round(a[2] + (b[2] - a[2]) * alpha))


def _layer(lightness: float, chroma: float, hue: float) -> tuple[int, int, int]:
    """Convert one biological layer into terminal RGB."""
    return oklab.oklch_to_srgb8(max(0.0, lightness), chroma, hue)


def _texture(request: _SampleRequest, seed: int) -> float:
    """One organic field sample for this cell.

    Returns a SINGLE value, not four. An earlier signature returned
    `(broad, fine, pearl, wave)` — four names implying four independent
    spatial frequencies — while handing back the same number four times. The
    output was correct and the shape was a lie, and it cost real time: a sweep
    of `broad * 0.95 + wave * 0.52` looked like two knobs and was one,
    `texture * 1.47`, so the tuning barely moved and the reason was invisible.

    Genuine multi-frequency texture (mottle / passing-cloud / pearl scatter at
    different octaves) is a real improvement available here, but it CHANGES THE
    LOOK, so it is Adam's call rather than a silent refactor.
    """
    return _field_sample(seed, request.x, request.row, request.time_ms)


def _set_terminal_ground(ground: tuple[int, int, int]) -> None:
    """Set the ground selected by the outer renderer for this render pass."""
    global _active_ground
    _active_ground = ground


_active_ground = TERMINAL_GROUND


@lru_cache(maxsize=512)
def _static_layers(session_id: str) -> tuple[tuple[int, int, int], tuple[int, int, int], palette.Palette]:
    """Cache identity layers that do not vary from cell to cell."""
    palette_value = palette.for_session(session_id)
    leuc = _layer(LEUCOPHORE_LIGHTNESS, LEUCOPHORE_CHROMA, palette_value.hue + 1.2)
    iri = _layer(IRIDOPHORE_LIGHTNESS, IRIDOPHORE_CHROMA, palette_value.hue + 4.0)
    return leuc, iri, palette_value


@lru_cache(maxsize=16384)
def _field_sample(seed: int, x: int, row: int, time_ms: float) -> float:
    """One organic field sample, memoised.

    Each cell is sampled twice — once to rank it within its pigment segment and
    once to render it — and the duplicate call was the cold-row budget: 18.5 ms
    against a 16.7 ms frame. Memoising drops the second to a dict lookup.
    """
    return noise.fractal(seed + 17, x * 0.075 + time_ms * NOISE_TIME_SCALE * 0.4, row * 0.27)


def _pigment_signal(seed: int, x: int, row: int, time_ms: float) -> float:
    """Rank one cell for pigment selection.

    Takes scalars, not a `_SampleRequest`: ranking touches every cell of every
    row, and building a frozen dataclass per cell to reach a single noise
    sample cost 5.1 ms/row against a 16.7 ms frame budget.
    """
    return _field_sample(seed, x, row, time_ms)


def _segment_width(width: int) -> int:
    """Return the fixed segment size for deterministic pigment density."""
    return PIGMENT_SEGMENT_WIDTH


@lru_cache(maxsize=2048)
def _pigment_winners(session_id: str, width: int, height: int,
                    row: int, time_ms: float) -> frozenset[int]:
    """Return selected x coordinates once for a whole render row."""
    winners: set[int] = set()
    seed = palette.seed_of(session_id)
    segment_width = _segment_width(width)
    for start in range(0, max(0, width), segment_width):
        stop = min(start + segment_width, width)
        if PIGMENT_TOP_K == 1:
            # The common case, and the hot one: max() is a single O(n) pass
            # where sorting the segment is O(n log n) for the same answer.
            winners.add(max(range(start, stop),
                            key=lambda x: (_pigment_signal(seed, x, row, time_ms), -x)))
            continue
        ranked = sorted(
            range(start, stop),
            key=lambda x: (-_pigment_signal(seed, x, row, time_ms), x),
        )
        winners.update(ranked[:PIGMENT_TOP_K])
    return frozenset(winners)


def _pigment_selected(request: _SampleRequest) -> bool:
    """Select exactly the strongest cells in the request's fixed segment."""
    return request.x in _pigment_winners(
        request.session_id, request.width, request.height, request.row, request.time_ms)


def _pigment_alpha(request: _SampleRequest) -> float:
    """Full pigment on the segment's winners, none anywhere else.

    Selecting the top-k WITHIN fixed segments fixes density by construction and
    bounds the dark gap between lit cells. A threshold on an absolute value
    cannot: it makes density seed-dependent, so some sessions render nearly
    blank and others nearly solid.
    """
    return PIGMENT_ALPHA_CEILING if _pigment_selected(request) else 0.0


def _field_layers(request: _SampleRequest) -> list[tuple[tuple[int, int, int], float, str]]:
    """Build the one canonical leucophore/iridophore/pigment stack."""
    leuc, iri, palette_value = _static_layers(request.session_id)
    texture = _texture(request, palette.seed_of(request.session_id))
    pigment_l = (PIGMENT_BASE_LIGHTNESS
                 + max(0.0, texture - 0.18) * 1.35
                 + max(0.0, texture - 0.58) * 0.62)
    pigment_c = PIGMENT_CHROMA + texture * 0.125
    pigment = _layer(pigment_l, pigment_c, palette_value.hue + (palette_value.accent - 0.5) * 1.4)
    return [(leuc, LEUCOPHORE_ALPHA, "leucophore"),
            (iri, IRIDOPHORE_ALPHA, "iridophore"),
            (pigment, _pigment_alpha(request), "chromatophore")]


def _composite(request: _SampleRequest, disable: str | None = None) -> tuple[int, int, int]:
    """Composite the canonical stack, optionally omitting one layer.

    An unselected cell short-circuits to the window colour: ~84% of cells carry
    no pigment, and compositing three OKLab layers only to snap the result back
    to the ground was most of the cold-row budget. Omitting a layer is a
    diagnostic, so it always takes the full path.
    """
    if disable is None and not _pigment_selected(request):
        return _active_ground
    out = (0, 0, 0)
    for color, alpha, name in _field_layers(request):
        if disable != name:
            out = _blend(out, color, max(0.0, alpha))
    return out


def _snap_to_window(rgb: tuple[int, int, int], *, selected: bool = False) -> tuple[int, int, int]:
    """Land an unlit cell exactly on the window colour.

    A field whose unlit ground merely APPROXIMATES the terminal background reads
    as a lighter panel laid over it, with visible edges wherever painting stops.
    Applied last, to the colour that actually reaches the screen.

    `selected` cells are EXEMPT. Pigment density is guaranteed by construction —
    the top-k cell of every fixed segment is lit — and a blanket luma test
    silently broke that guarantee: a winner that happened to be dark was snapped
    back to ground like any unlit cell. Measured on the shipped code, 8 of 24
    winners were erased in one row, which is what opened a 44-cell unlit gap
    against a ~25-cell ceiling. Whatever selection lights, snapping must not
    take away.

    The darkness test uses a cheap luma sum rather than a full OKLab transform:
    this runs once per cell, and the conversion cost showed up directly in the
    cold-row budget (measured 19.9 ms/row against a 16.7 ms frame).
    """
    if selected:
        return rgb
    if sum(rgb) <= GROUND_SNAP_LUMA:
        return _active_ground
    return rgb


def _contract(rgb: tuple[int, int, int], strength: float, fine: float) -> tuple[int, int, int]:
    """Move a cell toward a calm, hue-preserving contracted colour."""
    if strength <= 0.0:
        return rgb
    lab = oklab.srgb8_to_oklch(*rgb)
    # Quantising lightness into a few steps is what makes contraction CONVERGE.
    # Blending the original colour back in preserves every input distinction, so
    # a contracted row carried more tones than an open one — the inverse of the
    # design. Hue and chroma still ride through untouched.
    calm_l = CALM_LIGHTNESS + round((lab.L - CALM_LIGHTNESS) * CALM_LIGHTNESS_RETENTION
                                    * CALM_STEPS) / CALM_STEPS
    calm = _layer(calm_l, min(lab.chroma, CALM_CHROMA_FLOOR + fine * CALM_CHROMA_RANGE), lab.hue)
    return _blend(rgb, calm, strength)


def _request(session_id: str, x: int, y: int, width: int, height: int, row: int, time_ms: float) -> _SampleRequest:
    """Package public coordinates for internal helpers."""
    return _SampleRequest(session_id, x, y, width, height, row, time_ms)


def _finish(request: _SampleRequest, rgb: tuple[int, int, int],
            disable: str | None) -> tuple[int, int, int]:
    """Land a sampled colour on the screen.

    One seam for both samplers: a layer-disabled probe is returned raw so a test
    can see the layer it asked about, and every real cell goes through the snap
    with its selection state, so a winner is never erased on the way out.
    """
    if disable:
        return rgb
    return _snap_to_window(rgb, selected=_pigment_selected(request))


def sample(session_id: str, x: int, y: int, width: int, height: int,
           row: int, time_ms: float, disable: str | None = None) -> tuple[int, int, int]:
    """Sample one composited identity cell, optionally omitting a layer."""
    request = _request(session_id, x, y, width, height, row, time_ms)
    return _finish(request, _composite(request, disable), disable)


def sample_contracted(session_id: str, x: int, y: int, width: int, height: int,
                      row: int, time_ms: float, strength: float,
                      **options: str | None) -> tuple[int, int, int]:
    """Sample one cell and apply contraction strength to its canonical stack."""
    request = _request(session_id, x, y, width, height, row, time_ms)
    disable = options.get("disable")
    composited = _composite(request, disable)
    if strength <= 0.0:
        return _finish(request, composited, disable)
    # `strength` gates contraction; the mask supplies the finite support, so an
    # applied cell contracts at the mask centre. (The previous
    # `0.0 if strength > 0.0 else RADIUS` could not reach its else branch —
    # this line runs only when strength > 0.0.)
    fine = _texture(request, palette.seed_of(session_id))
    contracted = _contract(composited, contraction.weight(MASK_CENTRE), fine)
    return _finish(request, contracted, disable)


def clear_caches() -> None:
    """Clear field caches that may contain colours from an old terminal depth."""
    _static_layers.cache_clear()
    _field_sample.cache_clear()
    _pigment_winners.cache_clear()
