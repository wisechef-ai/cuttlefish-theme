"""Stable identity palettes."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import math

@dataclass(frozen=True)
class Palette:
    hue: float
    accent: float
    shade: float
    pearl: float

def seed_of(session_id: str) -> int:
    """Return a stable 32-bit digest-derived seed."""
    return int.from_bytes(hashlib.blake2s(session_id.encode('utf-8'), digest_size=4).digest(), 'little')

@lru_cache(maxsize=512)
def for_session(session_id: str) -> Palette:
    """Derive a hashable, session-specific palette."""
    digest = hashlib.blake2s(session_id.encode('utf-8'), digest_size=16).digest()
    vals = [int.from_bytes(digest[i:i+4], 'little') / 4294967296 for i in range(0, 16, 4)]
    return Palette(vals[0] * math.tau, vals[1], vals[2], vals[3])
