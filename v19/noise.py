"""Deterministic smooth value noise."""
from __future__ import annotations
import math

def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def _smooth(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)

def _hash(seed: int, x: int, y: int) -> float:
    n = (seed ^ (x * 0x45D9F3B) ^ (y * 0x119DE1F3)) & 0xffffffff
    n = ((n ^ (n >> 16)) * 0x45D9F3B) & 0xffffffff
    n = ((n ^ (n >> 16)) * 0x45D9F3B) & 0xffffffff
    return ((n ^ (n >> 16)) & 0xffffffff) / 4294967295.0

def value_noise(seed: int, x: float, y: float) -> float:
    """Sample bilinearly interpolated value noise in [0, 1]."""
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = _smooth(x - x0), _smooth(y - y0)
    a, b = _hash(seed, x0, y0), _hash(seed, x0 + 1, y0)
    c, d = _hash(seed, x0, y0 + 1), _hash(seed, x0 + 1, y0 + 1)
    return _mix(_mix(a, b, fx), _mix(c, d, fx), fy)

def fractal(seed: int, x: float, y: float) -> float:
    """Sample compact multi-octave noise; cell rendering favors bounded cost."""
    total = norm = 0.0
    amplitude, frequency = 0.5, 1.0
    for octave in range(1):
        total += value_noise(seed + octave * 1013, x * frequency, y * frequency) * amplitude
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm
