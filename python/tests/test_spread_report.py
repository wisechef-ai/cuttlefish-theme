"""Property run: 20 sessions arriving in 200 random orders, all live at once.

REPORTS (never asserts a threshold) the worst live-pair hue gap in centidegrees: the CONTRACT
documents that online farthest-point can only guarantee ~720 cd at 20 sessions.
Run with `-s` to see the line; it is also written to $CF_SPREAD_REPORT when set.
"""
import os
import random

from cuttlefish_theme.python.domain import allocator as A


def _min_gap(hues):
    return min(A.dist(a, b) for i, a in enumerate(hues) for b in hues[i + 1:])


def test_twenty_arrivals_over_200_random_orders_report_worst_gap():
    rnd = random.Random(2909)
    gaps = []
    for order in range(200):
        ids = [f"o{order}-{rnd.getrandbits(48):012x}" for _ in range(20)]
        rnd.shuffle(ids)
        hues = []
        for rid in ids:
            hues.append(A.allocate(rid, list(hues)).hue_cd)
        gaps.append(_min_gap(hues))
    worst, median = min(gaps), sorted(gaps)[len(gaps) // 2]
    line = f"worst_gap_cd_20={worst} median_gap_cd_20={median} best_gap_cd_20={max(gaps)} orders=200 arrivals=20"
    print("\nSPREAD-REPORT " + line)
    path = os.environ.get("CF_SPREAD_REPORT")
    if path:
        with open(path, "w") as f:
            f.write(line + "\n")
    assert len(gaps) == 200 and worst >= 0
