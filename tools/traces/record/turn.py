#!/usr/bin/env python3
"""Record `turn`: boot, one plain turn, one tool turn, clean exit.   python3 tools/traces/record/turn.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "boot -> plain turn -> terminal tool turn -> /exit (synthetic prompts)"

if __name__ == "__main__":
    with Recording("turn", notes=NOTES) as rec:
        t = rec.open_tui("A")
        assert rec.turn(t, "Reply with exactly: pong"), "plain turn did not end"
        assert rec.turn(t, "Use the terminal tool to run: echo cf2909-tool-ok . Then say done."), "tool turn did not end"
        rec.exit_tui(t)
