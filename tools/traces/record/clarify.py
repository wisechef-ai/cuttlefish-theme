#!/usr/bin/env python3
"""Record `clarify`: answered clarify, then Ctrl-C-cancelled clarify, then the question re-asked and answered.
   python3 tools/traces/record/clarify.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "clarify answered (Enter) -> clarify cancelled (Ctrl-C) -> asked again -> answered; matched on tool_call_id"


def clarify_wait(t, n):
    return t.wait_hook("pre_tool_call", n=n, timeout=240, tool_name="clarify")


if __name__ == "__main__":
    with Recording("clarify", notes=NOTES) as rec:
        t = rec.open_tui("A")
        t.line("Use the clarify tool to ask me: 'Which colour?' with choices red and blue. Do nothing else until I answer.")
        assert clarify_wait(t, 1), "no clarify #1"
        t.pump(6)                       # pending for a while: needs-you must hold
        t.send("\r")                    # answer = first choice
        assert t.wait_hook("post_tool_call", n=1, timeout=60, tool_name="clarify"), "clarify #1 never answered"
        rec.settle(t)
        t.line("Use the clarify tool again to ask me: 'Which fruit?' with choices apple and pear.")
        assert clarify_wait(t, 2), "no clarify #2"
        t.pump(5)
        t.send("\x03")                  # cancel: post_tool_call fires immediately
        assert t.wait_hook("post_tool_call", n=2, timeout=60, tool_name="clarify"), "clarify #2 cancel produced no post_tool_call"
        t.pump(10)                      # the model may re-ask on its own
        if t.count("pre_tool_call", tool_name="clarify") < 3:
            rec.settle(t, quiet=5)
            t.line("Please ask me that same fruit question again using the clarify tool.")
        assert clarify_wait(t, 3), "clarify was not re-asked"
        t.pump(5)
        t.send("\r")
        assert t.wait_hook("post_tool_call", n=3, timeout=60, tool_name="clarify"), "clarify #3 never answered"
        rec.settle(t)
        rec.exit_tui(t)
