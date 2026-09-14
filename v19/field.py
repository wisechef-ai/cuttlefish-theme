"""Cell-resolution three-layer cuttlefish skin field."""
from __future__ import annotations
import math
from . import contraction, noise, oklab, palette

def _blend(a: tuple[int,int,int], b: tuple[int,int,int], alpha: float) -> tuple[int,int,int]:
    alpha = max(0.0, min(1.0, alpha))
    return tuple(round(x + (y - x) * alpha) for x, y in zip(a, b))

def _layer(L: float, C: float, hue: float) -> tuple[int,int,int]:
    return oklab.oklch_to_srgb8(max(0.0, L), C, hue)

def _contract(rgb: tuple[int,int,int], strength: float, fine: float) -> tuple[int,int,int]:
    if strength <= 0.0:
        return rgb
    lab = oklab.srgb8_to_oklch(*rgb)
    calm_l = 0.36 + max(-0.012, min(0.012, (lab.L - 0.36) * 0.05))
    calm = _layer(calm_l, min(lab.chroma, 0.035 + fine * 0.035), lab.hue)
    return _blend(rgb, calm, strength)

def sample(session_id: str, x: int, y: int, width: int, height: int,
           row: int, time_ms: float, disable: str | None = None) -> tuple[int,int,int]:
    """Sample one composited cell, optionally omitting one skin layer."""
    p = palette.for_session(session_id)
    seed = palette.seed_of(session_id)
    nx, ny = x / max(1, width), y / max(1, height)
    t = time_ms * 0.000018
    broad = .5 + .5 * math.sin(seed * .000001 + nx * 7.1 + row * .17 + t)
    fine = .5 + .5 * math.sin(seed * .000003 + x * .91 + row * .37 + t * .4)
    pearl = fine
    wave = .5 + .5 * math.sin(nx * 15 + math.sin(row * .33 + t) * 1.7 + t * 3)
    leuc = _layer(.25, .055, p.hue + 1.2)
    iri = _layer(.06, .05, p.hue + 4.0)
    pigment_l = .025 + max(0.0, broad - .18) * 1.35 + max(0.0, wave - .58) * .62
    pigment = _layer(pigment_l, .08 + fine * .10 + pearl * .025, p.hue + (p.accent - .5) * 1.4)
    out = (0, 0, 0)
    if disable != 'leucophore': out = _blend(out, leuc, .88)
    if disable != 'iridophore': out = _blend(out, iri, .72)
    if disable != 'chromatophore': out = _blend(out, pigment, max(0.0, min(.76, broad * .95 + wave * .52 - .42)))
    return _contract(out, 1.0 if False else 0.0, fine)

def sample_contracted(session_id: str, x: int, y: int, width: int, height: int,
                      row: int, time_ms: float, strength: float,
                      disable: str | None = None) -> tuple[int,int,int]:
    """Sample and apply biological contraction to the resulting cell."""
    p = palette.for_session(session_id)
    seed = palette.seed_of(session_id)
    nx, ny = x / max(1, width), y / max(1, height)
    t = time_ms * 0.000018
    broad = .5 + .5 * math.sin(seed * .000001 + nx * 7.1 + row * .17 + t)
    fine = .5 + .5 * math.sin(seed * .000003 + x * .91 + row * .37 + t * .4)
    pearl = fine
    wave = .5 + .5 * math.sin(nx * 15 + math.sin(row * .33 + t) * 1.7 + t * 3)
    layers = [(_layer(.20 + broad*.13,.055,p.hue+1.2), .88, 'leucophore'),
              (_layer(.035+broad*.075+fine*.025,.035+broad*.045,p.hue+3.8+wave*.5), .72, 'iridophore'),
              (_layer(.025+max(0,broad-.18)*1.35+max(0,wave-.58)*.62,.08+fine*.10+pearl*.025,p.hue+(p.accent-.5)*1.4), max(0,min(.76,broad*.95+wave*.52-.42)), 'chromatophore')]
    out=(0,0,0)
    for color, alpha, name in layers:
        if disable != name: out = _blend(out, color, alpha)
    return _contract(out, strength, fine)
