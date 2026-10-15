#!/usr/bin/env python3
"""Record `review-verify`: a write_file turn fires pre_verify between the last post_tool_call and post_llm_call.
   python3 tools/traces/record/review_verify.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "write_file turn: pre_verify fires once (~100 ms before the turn ends); a plain turn before it fires none"

if __name__ == "__main__":
    with Recording("review-verify", notes=NOTES) as rec:
        t = rec.open_tui("A")
        assert rec.turn(t, "Reply with exactly: pong")
        assert t.count("pre_verify") == 0
        assert rec.turn(t, f"Use the write_file tool to create {rec.workspace}/hello.py containing a python hello world, then tell me it is done.")
        assert t.count("pre_verify") >= 1, "pre_verify never fired"
        rec.exit_tui(t)
