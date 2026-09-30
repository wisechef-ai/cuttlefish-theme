#!/usr/bin/env python3
"""Spike 13(a) control: bytes + CPU at rest AFTER the TUI is ready, for no-widget vs static mantle. Shows what the
host itself writes at rest (status-bar uptime counter) so the mantle's own contribution is the difference."""
import sys, os, shutil, time, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "_lib"))
from tui import Tui, make_home
HZ = os.sysconf("SC_CLK_TCK")
def run(withwidget):
    home = make_home()
    if withwidget:
        shutil.copy(f"{HERE}/mantle.mjs", f"{home}/tui-widgets/mantle13.mjs"); open(f"{home}/mantle-mode", "w").write("static")
    t = Tui(home, 120, 40); assert t.wait_for("ready", 200); t.pump(8)
    r = subprocess.run(f"pstree -apl {t.pid}", shell=True, capture_output=True, text=True).stdout
    pid = [int(l.split(",")[1].split()[0]) for l in r.splitlines() if "node-MainThread" in l.split(",")[0] or "node," in l.split(" ")[0]][0]
    st = lambda: (lambda f: int(f[11]) + int(f[12]))(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split())
    out = []
    for _ in range(3):
        t.raw.clear(); c0 = st(); w0 = time.time(); t.pump(10); dt = time.time() - w0
        out.append((len(t.raw), round(100 * (st() - c0) / HZ / dt, 2), bytes(t.raw)[:120]))
    t.close(); shutil.rmtree(home, ignore_errors=True); return out
for label, w in (("no-widget", False), ("static-mantle", True)):
    for b, c, sample in run(w): print(f"{label:14s} 10s window: bytes={b:4d} node_cpu={c}%  sample={sample!r}")
