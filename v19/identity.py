"""Stable, perceptually spaced identities for concurrent sessions."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from .. import session
from ..color.identity import IdentityColor, allocate
from ..color.oklab import OKLCh

# The six-session contract requires a comfortable 0.04 OKLab floor; the
# allocator's measured candidate search is the source of that spacing.
MIN_CONCURRENT_SEPARATION = 0.04
# WHY 96: the allocator's own default candidate count; named here so the
# signature does not carry a bare number the caller cannot interpret.
DEFAULT_CANDIDATE_COUNT = 96


def _oklab_to_oklch(colour: tuple[float, float, float]) -> OKLCh:
    """Convert an OKLab centroid to the allocator's degree-based OKLCh."""
    lightness, a_axis, b_axis = colour
    return OKLCh(lightness, math.hypot(a_axis, b_axis),
                 math.degrees(math.atan2(b_axis, a_axis)))


def _allocator_live(live: tuple[tuple[float, float, float], ...]) -> tuple[OKLCh, ...]:
    """Convert contract centroids into allocator-native colours."""
    return tuple(_oklab_to_oklch(colour) for colour in live)


def _as_oklab(identity_colour: IdentityColor) -> tuple[float, float, float]:
    """Convert an allocated degree-based OKLCh colour to an OKLab centroid."""
    oklch = identity_colour.oklch
    hue_radians = math.radians(oklch.h)
    return (oklch.L, oklch.C * math.cos(hue_radians),
            oklch.C * math.sin(hue_radians))


def identity_for(
    session_id: str,
    live: tuple[tuple[float, float, float], ...],
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
) -> tuple[float, float, float]:
    """Return a deterministic OKLab identity spaced from live centroids.

    DELIBERATELY NOT lru_cached. It was, at maxsize=4096, and the cache never
    hit once: `live` is part of the key and it changes every time a session
    appears, so no key ever repeated. Measured on a realistic desktop of six
    sessions painting forty rows each: hits=0, misses=13. A cache whose key
    never repeats is not a cache — it is a full recompute that also pays to
    hash the peer tuple on every call.

    The memo that does the real work is `renderer._observed_identities`, keyed
    on session id alone, which is why one session painting 200 rows costs 8
    allocations rather than 200.
    """
    allocated = allocate(session_id, _allocator_live(live),
                         min_distance=MIN_CONCURRENT_SEPARATION,
                         candidate_count=candidate_count)
    return _as_oklab(allocated)


def live_identities(path: Path | None = None) -> tuple[tuple[float, float, float], ...]:
    """Return current registry identities as OKLab centroids, never raising."""
    try:
        live_sessions = session.read_registry(path)
    except Exception:
        return ()
    identities: list[tuple[float, float, float]] = []
    for live_session in live_sessions:
        identities.append(identity_for(live_session.session_id, tuple(identities)))
    return tuple(identities)
