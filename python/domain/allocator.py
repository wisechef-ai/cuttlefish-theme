"""CONTRACT (packages/core/CONTRACT.md) §1 — identity allocator. Identity is a hue SLOT: 20 slots on [110, 340).

Pure: no clock, no randomness, no I/O. Mirrors packages/core/domain/identity.ts exactly."""
import hashlib
from collections import namedtuple

ARC_START = 110.0   # degrees, inclusive (tokens.identity.hue_arc_deg)
ARC_END = 340.0     # exclusive
SLOTS = 20
STEP = (ARC_END - ARC_START) / SLOTS    # 11.5
CAP = 3             # slot distance beyond which spacing is "far enough"
NAME_MAX = 16

Allocation = namedtuple("Allocation", "slot hue_deg crowded")


def is_slot(k):
    return isinstance(k, int) and not isinstance(k, bool) and 0 <= k < SLOTS


def hue_of_slot(k):
    """115.75 ... 334.25 (exact in binary64)."""
    if not is_slot(k):
        raise ValueError(f"slot must be an integer in 0..{SLOTS - 1}, got {k!r}")
    return ARC_START + STEP * (k + 0.5)


def _digest(lineage_root):
    return hashlib.blake2b(lineage_root.encode("utf-8"), digest_size=32).digest()


def _require_root(lineage_root):
    if not isinstance(lineage_root, str) or not lineage_root.strip():
        raise ValueError("lineage root is empty: degrade to unbound, never guess an identity")


def preferred(lineage_root):
    """First 8 bytes (big endian) of blake2b-256(utf8(root)) mod 20."""
    _require_root(lineage_root)
    return int.from_bytes(_digest(lineage_root)[:8], "big") % SLOTS


def allocate(lineage_root, peers):
    """Pick a slot given the slots held by OTHER live sessions (duplicates allowed, order irrelevant).

    Capped farthest-point over the free slots: far enough first, then closest to the hash, then the
    lowest index. All slots taken: the hash slot repeats and ``crowded`` is surfaced, never hidden."""
    pref = preferred(lineage_root)
    peers = list(peers)
    for p in peers:
        if not is_slot(p):
            raise ValueError(f"peer slot must be an integer in 0..{SLOTS - 1}, got {p!r}")
    if not peers:
        return Allocation(pref, round(hue_of_slot(pref), 2), False)
    held = set(peers)
    free = [k for k in range(SLOTS) if k not in held]
    if not free:
        return Allocation(pref, round(hue_of_slot(pref), 2), True)
    best = max(free, key=lambda k: (min(CAP, min(abs(k - p) for p in held)), -abs(k - pref), -k))
    return Allocation(best, round(hue_of_slot(best), 2), False)


def trim_name(text):
    return (text or "").strip()[:NAME_MAX]


def default_name(lineage_root):
    return "s-" + _digest(lineage_root).hex()[0:4]
