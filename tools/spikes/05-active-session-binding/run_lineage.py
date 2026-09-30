#!/usr/bin/env python
"""Spike 05b: single TUI, isolated diagnostics for /new, /resume, forced ROTATING compression.
compression: in_place false, protect_last_n 2, protect_first_n 1, threshold tiny -> real rotation.
Usage: run_lineage.py OUTDIR"""
import sys, os, time, json, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import *  # noqa
sys.argv += [""]
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
LOG = open(f"{out}/05-lineage.log", "w")
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.write(s + "\n"); LOG.flush()

def af(t):
    def desc(pid):
        r = []
        for l in subprocess.run(["ps", "-e", "-o", "pid=,ppid="], capture_output=True, text=True).stdout.splitlines():
            p, pp = map(int, l.split())
            if pp == pid: r.append(p); r += desc(p)
        return r
    for pid in [t.p.pid] + desc(t.p.pid):
        try: env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
        except OSError: continue
        for kv in env:
            if kv.startswith(b"HERMES_TUI_ACTIVE_SESSION_FILE="): return kv.split(b"=", 1)[1].decode()
import subprocess
home = make_home(extra_cfg="compression:\n  in_place: false\n  protect_last_n: 2\n  protect_first_n: 1\n  threshold: 0.5\n")
dump_home = home
enable_plugin(home, "hookdump", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "06-hook-payloads", "hookdump"))
dump = f"{out}/lineage-hooks.jsonl"
t = Tui(home, "A", HOOKDUMP_FILE=dump); assert boot(t)
f = af(t)
def state(label):
    c = sqlite3.connect(f"file:{home}/state.db?mode=ro", uri=True)
    rows = c.execute("select id,parent_session_id,end_reason,message_count from sessions order by started_at").fetchall()
    say(f"--- {label}\n   file={open(f).read() if os.path.exists(f) and open(f).read() else '<EMPTY/MISSING>'}")
    for r in rows: say("   db:", r)
def turn(msg):
    t.line(msg); wait_idle(t)
state("boot")
turn("Reply with exactly: one"); state("after turn 1 (=id1)")
first = json.loads(open(f).read())["session_id"]
t.send("/new"); time.sleep(1); t.send("\r"); t.pump(3); t.send("y"); t.pump(8)
say("SCREEN after /new:\n" + "\n".join(t.text().splitlines()[-8:])); state("after /new (no turn yet)")
turn("Reply with exactly: two"); state("after /new + turn (=id2)")
for i in range(6): turn(f"Write a 40 word sentence about the number {i}.")
state("after 6 more turns")
t.send(f"/resume {first}"); time.sleep(1); t.send("\r"); t.pump(10)
say("SCREEN after /resume:\n" + "\n".join(t.text().splitlines()[-8:])); state(f"after /resume {first}")
for i in range(3): turn(f"Write a 40 word sentence about the colour {i}.")
t.send("/compress"); time.sleep(1); t.send("\r"); t.pump(20); wait_idle(t, 240)
say("SCREEN after /compress:\n" + "\n".join(t.text().splitlines()[-8:])); state("after /compress")
turn("Reply with exactly: post"); state("after turn post-compress")
t.line("/exit"); t.pump(6)
say("exit: file exists:", os.path.exists(f))
rows = [json.loads(l) for l in open(dump)]
for r in rows:
    if r["hook"] in ("on_session_start", "on_session_end", "on_session_finalize", "on_session_reset", "pre_llm_call"):
        say("HOOK", r["hook"], r["ids"].get("session_id"), {k: r["ids"][k] for k in ("parent_session_id", "completed") if k in r["ids"]})
say("HOME", home)
