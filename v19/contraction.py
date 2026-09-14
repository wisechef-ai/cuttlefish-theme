"""Finite-support contraction mask."""
from __future__ import annotations
RADIUS = 48.0

def weight(distance: float) -> float:
    """Return a smooth contraction weight with exact finite support."""
    if distance <= 0.0:
        return 1.0
    if distance >= RADIUS:
        return 0.0
    t = 1.0 - distance / RADIUS
    return t * t * (3.0 - 2.0 * t)
