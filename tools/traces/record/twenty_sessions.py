#!/usr/bin/env python3
"""Record `twenty-sessions`: 20 TUI sessions in ONE home, 5 alive at the same time in the first wave, each with >= 1 turn.
   python3 tools/traces/record/twenty_sessions.py"""
import concurrent.futures as cf
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "20 sessions in one home; first 5 are held alive together (barrier) before any turn; then waves of 5 concurrent workers"
WIDTH = 5

if __name__ == "__main__":
    barrier = threading.Barrier(WIDTH)

    with Recording("twenty-sessions", notes=NOTES) as rec:
        def work(i):
            t = rec.open_tui("A")
            if i < WIDTH:
                barrier.wait(timeout=600)   # all of wave 1 is booted and bound before the first turn
            ok = rec.turn(t, f"Reply with exactly: {i}")
            rec.exit_tui(t)
            return ok

        with cf.ThreadPoolExecutor(WIDTH) as ex:
            results = list(ex.map(work, range(20)))
        assert all(results), results
