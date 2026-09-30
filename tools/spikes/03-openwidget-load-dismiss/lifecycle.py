#!/usr/bin/env python3
import sys, os, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "_lib"))
from tui import Tui, make_home
home = make_home(); shutil.copy(f"{HERE}/lifecycle_probe.mjs", f"{home}/tui-widgets/lc.mjs")
t = Tui(home, 120, 30); t0 = time.time(); seen = None
while time.time() - t0 < 240:
    t.pump(0.25)
    vis = "LIFECYCLE-CARD" in t.text()
    if vis != seen: print(f"t+{time.time()-t0:5.1f}s visible={vis}"); seen = vis
    if seen and time.time() - t0 > 20: break
print(open(f"{home}/lifecycle.log").read() if os.path.exists(f"{home}/lifecycle.log") else "NOLOG"); print(t.text()[-1500:]); print(os.listdir(home))
t.close(); shutil.rmtree(home, ignore_errors=True)
