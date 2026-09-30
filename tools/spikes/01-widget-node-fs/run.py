#!/usr/bin/env python3
"""Spike 01: node:fs import + fs.watch inside the real `hermes --tui`. One command: run.py [outdir]"""
import sys, os, json, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_lib"))
from tui import Tui, make_home
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-01"
os.makedirs(out, exist_ok=True)
home = make_home()
json.dump({"value": "alpha"}, open(f"{home}/cf-value.json", "w"))
shutil.copy(f"{HERE}/fsprobe.mjs", f"{home}/tui-widgets/fsprobe.mjs")
t = Tui(home, 120, 30)
ok1 = t.wait_for("FSVALUE=alpha", 150)
shot = lambda n: open(f"{out}/{n}.txt", "w").write("\n".join(l.rstrip() for l in t.screen.display))
t.pump(1); shot("before")
print("before: found FSVALUE=alpha =", ok1)
print([l.strip() for l in t.screen.display if "FSVALUE" in l])
json.dump({"value": "bravo"}, open(f"{home}/cf-value.json", "w"))
ok2 = t.wait_for("FSVALUE=bravo", 10); t.pump(1); shot("after")
print("after: found FSVALUE=bravo =", ok2)
print([l.strip() for l in t.screen.display if "FSVALUE" in l])
# atomic rename write (editor style)
json.dump({"value": "charlie"}, open(f"{home}/cf-value.tmp", "w")); os.rename(f"{home}/cf-value.tmp", f"{home}/cf-value.json")
ok3 = t.wait_for("FSVALUE=charlie", 10)
print("atomic-rename: found FSVALUE=charlie =", ok3)
print([l.strip() for l in t.screen.display if "FSVALUE" in l])
log = open(f"{home}/logs/tui_gateway_crash.log").read() if os.path.exists(f"{home}/logs/tui_gateway_crash.log") else "(no crash log)"
print("crash log:", log[:200])
t.close(); shutil.rmtree(home, ignore_errors=True)
print("RESULT", json.dumps({"initial": ok1, "modify": ok2, "atomic_rename": ok3}))
sys.exit(0 if ok1 and ok2 and ok3 else 1)
