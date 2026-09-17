"""OKLab/OKLCH conversion at the terminal colour boundary."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class OKLCH:
    L: float
    chroma: float
    hue: float

def _srgb_to_linear(value: float) -> float:
    value /= 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

def _linear_to_srgb(value: float) -> int:
    value = max(0.0, min(1.0, value))
    encoded = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255)

def oklch_to_srgb8(L: float, C: float, hue: float) -> tuple[int, int, int]:
    """Convert OKLCH to clipped 8-bit sRGB."""
    a, b = C * math.cos(hue), C * math.sin(hue)
    l_ = L + 0.3963377774*a + 0.2158037573*b
    m_ = L - 0.1055613458*a - 0.0638541728*b
    s_ = L - 0.0894841775*a - 1.2914855480*b
    l, m, s = l_**3, m_**3, s_**3
    return tuple(_linear_to_srgb(v) for v in (
        4.0767416621*l - 3.3077115913*m + 0.2309699292*s,
        -1.2684380046*l + 2.6097574011*m - 0.3413193965*s,
        -0.0041960863*l - 0.7034186147*m + 1.7076147010*s))

def srgb8_to_oklch(r: int, g: int, b: int) -> OKLCH:
    """Convert 8-bit sRGB to OKLCH."""
    r, g, b = (_srgb_to_linear(v) for v in (r, g, b))
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    L = 0.2104542553*l + 0.7936177850*m - 0.0040720468*s
    a = 1.9779984951*l - 2.4285922050*m + 0.4505937099*s
    bb = 0.0259040371*l + 0.7827717662*m - 0.8086757660*s
    return OKLCH(L, math.hypot(a, bb), math.atan2(bb, a))
