#!/usr/bin/env python3
"""Record `approval`: manual approvals, one 'once' (Enter) and one 'deny' (quick-pick 4).
   python3 tools/traces/record/approval.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "approvals.mode=manual: pre_approval_request -> post_approval_response(once) ; again -> post_approval_response(deny)"
ASK = "Use the terminal tool to run exactly this command and nothing else: rm -rf /tmp/cf2909-approval-probe-dir"

if __name__ == "__main__":
    with Recording("approval", notes=NOTES, extra_cfg={"A": "approvals:\n  mode: manual\n"}) as rec:
        t = rec.open_tui("A")
        t.line(ASK)
        assert t.wait_hook("pre_approval_request", n=1, timeout=240), "no approval request #1"
        t.pump(5)                       # pending: needs-you must hold
        t.send("\r")                    # default = once
        assert t.wait_hook("post_approval_response", n=1, timeout=60), "approval #1 unanswered"
        rec.settle(t)
        t.line(ASK)
        assert t.wait_hook("pre_approval_request", n=2, timeout=240), "no approval request #2"
        t.pump(4)
        t.send("4")                     # quick-pick 4 = deny
        assert t.wait_hook("post_approval_response", n=2, timeout=60), "approval #2 unanswered"
        rec.settle(t)
        rec.exit_tui(t)
