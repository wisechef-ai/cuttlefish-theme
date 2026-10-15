#!/usr/bin/env python3
"""Record `two-profiles`: two HERMES_HOMEs (A, B), turns interleaved A -> B -> A -> B, then a second session in A.
   python3 tools/traces/record/two_profiles.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "profile A and B alive together; turns interleave A,B,A,B; then a new session in A; identity must stay per profile"

if __name__ == "__main__":
    with Recording("two-profiles", profiles=("A", "B"), notes=NOTES) as rec:
        a1 = rec.open_tui("A")
        assert rec.turn(a1, "Reply with exactly: a1")
        b1 = rec.open_tui("B")
        assert rec.turn(b1, "Reply with exactly: b1")
        assert rec.turn(a1, "Reply with exactly: a2")
        assert rec.turn(b1, "Reply with exactly: b2")
        a2 = rec.open_tui("A")
        assert rec.turn(a2, "Reply with exactly: a3")
        rec.exit_tui(b1)
        rec.exit_tui(a1)
        rec.exit_tui(a2)
