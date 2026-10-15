#!/usr/bin/env python3
"""Record `crash-kill9`: SIGKILL the TUI owner and its gateway child (whole process group) mid-turn. Heartbeats stop, pid_dead is observed, the stale bound file remains.
   python3 tools/traces/record/crash_kill9.py"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "SIGKILL (process group: TUI owner + gateway) mid-turn: no hook fires for the death; heartbeat stops, pid_dead is the last line (replay now may be advanced past it)"

if __name__ == "__main__":
    with Recording("crash-kill9", notes=NOTES) as rec:
        t = rec.open_tui("A")
        rec.turn(t, "Reply with exactly: pong")
        t.line("Write a 600 word essay about octopuses.")
        assert t.wait_hook("pre_llm_call", n=2, timeout=120), "turn did not start"
        assert t.wait_hook("on_stream_start", n=2, timeout=120), "turn never streamed"
        t.pump(3)
        os.killpg(t.pid, signal.SIGKILL)   # node AND its tui_gateway child: nothing is left to fire a shutdown hook
        end = time.time() + 32
        while time.time() < end:
            t.pump(0.5)
            time.sleep(0.5)
        assert not t.alive()
