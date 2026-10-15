"""Property run: 20 sessions arriving in 200 random orders, all live at once, then 16.

With the 20-slot lattice the worst live-pair hue gap is the slot spacing (11.5 deg) whenever no slot repeats,
whatever the arrival order. REPORTS the numbers (run with -s; also written to $CF_SPREAD_REPORT when set)."""
import os
import random

from cuttlefish_theme.python.domain import allocator as A


def _min_gap(hues):
    return min(abs(a - b) for i, a in enumerate(hues) for b in hues[i + 1:])


def _arrive(rnd, n, order):
    slots = []
    for _ in range(n):
        slots.append(A.allocate(f"o{order}-{rnd.getrandbits(48):012x}", list(slots)).slot)
    return slots


def test_twenty_arrivals_over_200_random_orders_never_collide_and_report_worst_gap():
    rnd = random.Random(2909)
    gaps20, gaps16 = [], []
    for order in range(200):
        s20 = _arrive(rnd, 20, order)
        assert sorted(s20) == list(range(20))          # every slot taken exactly once, no crowding
        gaps20.append(_min_gap([A.hue_of_slot(k) for k in s20]))
        s16 = _arrive(rnd, 16, order)
        assert len(set(s16)) == 16
        gaps16.append(_min_gap([A.hue_of_slot(k) for k in s16]))
    line = (f"worst_gap_deg_20={min(gaps20)} worst_gap_deg_16={min(gaps16)} "
            f"best_gap_deg_16={max(gaps16)} orders=200")
    print("\nSPREAD-REPORT " + line)
    path = os.environ.get("CF_SPREAD_REPORT")
    if path:
        with open(path, "w") as f:
            f.write(line + "\n")
    assert min(gaps20) == A.STEP == 11.5 and min(gaps16) >= A.STEP
