#!/usr/bin/env python
"""Spike 06b: approval request + compression-rotation hooks, each in a FRESH home (06's main run had a
stray pending clarify muddying the approval turn, and default compression is in_place=true -> no rotation).
Usage: run_extra.py OUTDIR"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import *  # noqa
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1]
os.makedirs(f"{out}/screens", exist_ok=True)


def snap(t, n): open(f"{out}/screens/{n}.txt", "w").write(t.text())


def mark(d, l):
    open(d, "a").write(json.dumps({"hook": "@@MARK", "label": l, "ts": round(time.time(), 3)}) + "\n"); print("MARK", l, flush=True)


def approval():
    h = make_home(extra_cfg="approvals:\n  mode: manual\n")
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    d = f"{out}/approval.jsonl"
    t = Tui(h, "p", HOOKDUMP_FILE=d); assert boot(t)
    mark(d, "approval-asked")
    t.line("Use the terminal tool to run exactly this command and nothing else: rm -rf /tmp/cf2909-approval-probe-dir")
    ok = t.wait_for(r"(?i)dangerous|approval|allow|deny", 150); t.pump(3); snap(t, "30-approval-open")
    mark(d, f"approval-visible={ok}"); time.sleep(6)
    mark(d, "approval-still-pending-6s"); snap(t, "31-approval-pending")
    t.send("\x1b[B"); t.pump(1); t.send("\x1b[B"); t.pump(1); t.send("\x1b[B"); t.pump(1); t.send("\r")   # move to deny (best effort)
    mark(d, "approval-answered(deny)"); wait_idle(t, 90); snap(t, "32-approval-answered")
    t.line("/exit"); t.pump(4); t.p.terminate(force=True); return h


def rotate():
    h = make_home(extra_cfg="compression:\n  in_place: false\n")
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    d = f"{out}/rotate.jsonl"
    t = Tui(h, "r", HOOKDUMP_FILE=d); assert boot(t)
    mark(d, "turn1"); t.line("Reply with exactly: one"); wait_idle(t)
    mark(d, "turn2"); t.line("Reply with exactly: two"); wait_idle(t)
    mark(d, "compress"); t.line("/compress"); t.pump(15); wait_idle(t, 180); snap(t, "40-compress")
    mark(d, "post-compress-turn"); t.line("Reply with exactly: three"); wait_idle(t); snap(t, "41-post")
    mark(d, "exit"); t.line("/exit"); t.pump(5); t.p.terminate(force=True); return h


print("approval home", approval(), flush=True)
print("rotate home", rotate(), flush=True)
print("DONE")
