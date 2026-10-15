"""CONTRACT §1 — identity allocator, ``cf2909.identity/1``. Integer arithmetic only."""
import hashlib
from collections import namedtuple

GRID = 64
ARC_LO_CD = 11000
ARC_SPAN_CD = 23000
FULL_CD = 36000
NAME_MAX = 16

Allocation = namedtuple("Allocation", "hue_cd k base digest_hex")


def cand(k):
    return ARC_LO_CD + (ARC_SPAN_CD * (2 * k + 1)) // (2 * GRID)


def digest(lineage_root):
    return hashlib.blake2b(lineage_root.encode("utf-8"), digest_size=8).digest()


def base_of(lineage_root):
    return digest(lineage_root)[7] & 63


def dist(a, b):
    d = abs(a - b)
    return min(d, FULL_CD - d)


def allocate(lineage_root, peers_cd):
    d = digest(lineage_root)
    base = d[7] & 63
    peers = list(peers_cd)
    if not peers:
        k_star = base
    else:
        k_star, best = base, -1
        for j in range(GRID):
            k = (base + j) % GRID
            c = cand(k)
            score = min(dist(c, p) for p in peers)
            if score > best:
                k_star, best = k, score
    return Allocation(cand(k_star), k_star, base, d.hex())


def trim_name(text):
    return (text or "").strip()[:NAME_MAX]


def default_name(lineage_root):
    return "s-" + digest(lineage_root).hex()[0:4]
