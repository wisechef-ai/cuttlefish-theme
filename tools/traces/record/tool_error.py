#!/usr/bin/env python3
"""Record `tool-error`: tools that fail (non-zero exit, missing file) are NOT faults.   python3 tools/traces/record/tool_error.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "terminal command exits non-zero + read_file on a missing file: the turn still ends normally (no api_request_error)"

if __name__ == "__main__":
    with Recording("tool-error", notes=NOTES) as rec:
        t = rec.open_tui("A")
        assert rec.turn(t, "Use the terminal tool to run: ls /nonexistent-cf2909-dir . Then tell me what happened."), "turn 1"
        assert rec.turn(t, "Use the read_file tool on the path /nonexistent-cf2909-dir/missing.txt and tell me what happened."), "turn 2"
        assert t.count("post_tool_call") >= 2
        rec.exit_tui(t)
