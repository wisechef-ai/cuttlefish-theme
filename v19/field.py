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
PIGMENT_BASE_LIGHTNESS = 0.025
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
NOISE_TIME_SCALE = 0.000018

# The colour the theme sets as the terminal's OSC-11 background. Cells with no
# pigment MUST land here exactly: a field whose unlit ground differs from the
# window behind it reads as a lighter PANEL laid on the terminal, with visible
# edges wherever painting stops. Measured before this was pinned: per-session
# grounds of #050a09 / #05090e against a #0B0C10 window.
TERMINAL_GROUND = (0x0B, 0x0C, 0x10)

# Below this composited lightness a cell carries no visible pigment, so it is
# snapped to the window colour rather than left a near-miss.
GROUND_SNAP_LIGHTNESS = 0.11


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


def _texture(request: _SampleRequest, seed: int) -> tuple[float, float, float, float]:
    """Return broad, fine, pearl, and wave organic texture signals."""
    nx = request.x / max(1, request.width)
    t = request.time_ms * NOISE_TIME_SCALE
    texture = noise.fractal(seed + 17, request.x * 0.075 + t * 0.4, request.row * 0.27)
    broad = texture
    fine = texture
    # WHY: reusing one sampled field preserves motion at cell speed cheaply.
    wave = texture
    return broad, fine, fine, wave


@lru_cache(maxsize=512)
def _static_layers(session_id: str) -> tuple[tuple[int, int, int], tuple[int, int, int], palette.Palette]:
    """Cache identity layers that do not vary from cell to cell."""
    palette_value = palette.for_session(session_id)
    leuc = _layer(LEUCOPHORE_LIGHTNESS, LEUCOPHORE_CHROMA, palette_value.hue + 1.2)
    iri = _layer(IRIDOPHORE_LIGHTNESS, IRIDOPHORE_CHROMA, palette_value.hue + 4.0)
    return leuc, iri, palette_value


def _field_layers(request: _SampleRequest) -> list[tuple[tuple[int, int, int], float, str]]:
    """Build the one canonical leucophore/iridophore/pigment stack."""
    leuc, iri, palette_value = _static_layers(request.session_id)
    broad, fine, pearl, wave = _texture(request, palette.seed_of(request.session_id))
    pigment_l = PIGMENT_BASE_LIGHTNESS + max(0.0, broad - 0.18) * 1.35 + max(0.0, wave - 0.58) * 0.62
    pigment_c = PIGMENT_CHROMA + fine * 0.10 + pearl * 0.025
    pigment = _layer(pigment_l, pigment_c, palette_value.hue + (palette_value.accent - 0.5) * 1.4)
    return [(leuc, LEUCOPHORE_ALPHA, "leucophore"),
            (iri, IRIDOPHORE_ALPHA, "iridophore"),
            (pigment, min(PIGMENT_ALPHA_CEILING, broad * 0.95 + wave * 0.52 - 0.42), "chromatophore")]


def _composite(request: _SampleRequest, disable: str | None = None) -> tuple[int, int, int]:
    """Composite the canonical stack, optionally omitting one layer.

    Snapping happens in `_snap_to_window`, applied to the colour that actually
    reaches the screen — contraction runs after this and would otherwise move a
    snapped cell straight back off the window colour.
    """
    out = (0, 0, 0)
    for color, alpha, name in _field_layers(request):
        if disable != name:
            out = _blend(out, color, max(0.0, alpha))
    return out


def _snap_to_window(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Land an unlit cell exactly on the window colour.

    A field whose unlit ground merely APPROXIMATES the terminal background reads
    as a lighter panel laid over it, with visible edges wherever painting stops.
    Applied last, to the colour that actually reaches the screen.
    """
    if oklab.srgb8_to_oklch(*rgb).L < GROUND_SNAP_LIGHTNESS:
        return TERMINAL_GROUND
    return rgb


def _contract(rgb: tuple[int, int, int], strength: float, fine: float) -> tuple[int, int, int]:
    """Move a cell toward a calm, hue-preserving contracted colour."""
    if strength <= 0.0:
        return rgb
    lab = oklab.srgb8_to_oklch(*rgb)
    calm_l = 0.36 + max(-0.012, min(0.012, (lab.L - 0.36) * 0.05))
    calm = _layer(calm_l, min(lab.chroma, 0.035 + fine * 0.035), lab.hue)
    return _blend(rgb, calm, strength)


def _request(session_id: str, x: int, y: int, width: int, height: int, row: int, time_ms: float) -> _SampleRequest:
    """Package public coordinates for internal helpers."""
    return _SampleRequest(session_id, x, y, width, height, row, time_ms)


def sample(session_id: str, x: int, y: int, width: int, height: int,
           row: int, time_ms: float, disable: str | None = None) -> tuple[int, int, int]:
    """Sample one composited identity cell, optionally omitting a layer."""
    request = _request(session_id, x, y, width, height, row, time_ms)
    composited = _composite(request, disable)
    return composited if disable else _snap_to_window(composited)


def sample_contracted(session_id: str, x: int, y: int, width: int, height: int,
                      row: int, time_ms: float, strength: float,
                      **options: str | None) -> tuple[int, int, int]:
    """Sample one cell and apply contraction strength to its canonical stack."""
    request = _request(session_id, x, y, width, height, row, time_ms)
    disable = options.get("disable")
    composited = _composite(request, disable)
    if strength <= 0.0:
        return composited if disable else _snap_to_window(composited)
    fine = _texture(request, palette.seed_of(session_id))[1]
    # WHY: the public strength is a signal; the mask supplies finite support.
    distance = 0.0 if strength > 0.0 else contraction.RADIUS
    contracted = _contract(composited, contraction.weight(distance), fine)
    return contracted if disable else _snap_to_window(contracted)
