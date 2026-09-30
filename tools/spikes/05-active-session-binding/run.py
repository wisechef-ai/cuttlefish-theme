#!/usr/bin/env python
"""Spike 05: HERMES_TUI_ACTIVE_SESSION_FILE binding with TWO concurrent `hermes --tui` on ONE temp HERMES_HOME.
Usage: run.py OUTDIR [in_place=true|false]
Discovers each process's file via /proc/<node pid>/environ (what a widget child would inherit),
then records file content + state.db lineage after: boot, first turn, /new, /resume <old>, /compress, exit, SIGKILL."""
import sys, os, time, json, tempfile, sqlite3, signal, subprocess, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import *  # noqa

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cf05-out-")
in_place = (sys.argv[2] if len(sys.argv) > 2 else "false").lower()
os.makedirs(out, exist_ok=True)
LOG = open(f"{out}/05-{'inplace' if in_place == 'true' else 'rotate'}.log", "w")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True); LOG.write(s + "\n"); LOG.flush()


def descendants(pid):
    res = []
    for line in subprocess.run(["ps", "-e", "-o", "pid=,ppid="], capture_output=True, text=True).stdout.splitlines():
        p, pp = map(int, line.split())
        if pp == pid:
            res.append(p); res += descendants(p)
    return res


def active_file(t):
    """Return (pid, path) of the process in t's tree that carries HERMES_TUI_ACTIVE_SESSION_FILE."""
    for pid in [t.p.pid] + descendants(t.p.pid):
        try:
            env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
        except OSError:
            continue
        for kv in env:
            if kv.startswith(b"HERMES_TUI_ACTIVE_SESSION_FILE="):
                return pid, kv.split(b"=", 1)[1].decode()
    return None, None


def content(path):
    if not path or not os.path.exists(path):
        return "<MISSING>"
    s = open(path).read()
    return s if s else "<EMPTY>"


def sessions(home):
    c = sqlite3.connect(f"file:{home}/state.db?mode=ro", uri=True)
    return c.execute("select id,parent_session_id,end_reason,message_count,started_at from sessions order by started_at").fetchall()


def report(label, home, **tuis):
    say(f"\n--- {label}")
    for n, t in tuis.items():
        pid, path = active_file(t)
        say(f"  {n}: alive={t.p.isalive()} node_pid={pid} file={path}")
        say(f"     content={content(path)}")
    for r in sessions(home):
        say("  db:", r[:4])


home = make_home(extra_cfg=f"compression:\n  in_place: {in_place}\n  threshold: 0.5\n")
say(f"HOME {home}  compression.in_place={in_place}")
A = Tui(home, "A"); assert boot(A), "A boot"
B = Tui(home, "B"); assert boot(B), "B boot"
report("after boot (both idle, no turn yet)", home, A=A, B=B)
pa, fa = active_file(A); pb, fb = active_file(B)
say("distinct files:", fa != fb, "| same dir:", os.path.dirname(fa) == os.path.dirname(fb), "| mode:", oct(os.stat(fa).st_mode & 0o777))

A.line("Reply with exactly: alpha"); wait_idle(A)
B.line("Reply with exactly: bravo"); wait_idle(B)
report("(a) after first turn in each", home, A=A, B=B)
a1 = json.loads(content(fa))["session_id"] if content(fa).startswith("{") else None

A.line("/new"); A.pump(6)
A.line("Reply with exactly: alpha-two"); wait_idle(A)
report("(a') A after /new + turn (new session)", home, A=A, B=B)
a2 = json.loads(content(fa))["session_id"] if content(fa).startswith("{") else None

if a1:
    A.line(f"/resume {a1}"); A.pump(10)
    report(f"(b) A after /resume {a1} (older session)", home, A=A, B=B)

A.line("Reply with exactly: alpha-three"); wait_idle(A)
A.line("/compress"); A.pump(15); wait_idle(A, 180)
report("(c) A after /compress", home, A=A, B=B)
A.line("Reply with exactly: post-compress"); wait_idle(A)
report("(c') A after a turn following /compress", home, A=A, B=B)

# (d) exit
A.line("/exit"); A.pump(8)
say("\n--- (d) A exited cleanly: alive=", A.p.isalive(), "file exists:", os.path.exists(fa))
B_children = descendants(B.p.pid)
os.kill(B.p.pid, signal.SIGKILL)   # hard-kill the python launcher (no finally block)
time.sleep(2)
say("--- (d') B python launcher SIGKILLed: file exists:", os.path.exists(fb), "content:", content(fb))
for c in B_children:
    try: os.kill(c, signal.SIGKILL)
    except OSError: pass
say("DONE")
