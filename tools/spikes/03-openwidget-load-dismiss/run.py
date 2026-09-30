#!/usr/bin/env python3
"""Spike 03: auto-dock at load, dismiss, persist across restart, re-enable. One command: run.py [outdir]"""
import sys, os, json, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_lib"))
from tui import Tui, make_home
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-03"; os.makedirs(out, exist_ok=True)
home = make_home(); shutil.copy(f"{HERE}/mantle.mjs", f"{home}/tui-widgets/mantle.mjs")
state = lambda: open(f"{home}/plugins/cuttlefish/state.json").read() if os.path.exists(f"{home}/plugins/cuttlefish/state.json") else "(none)"
res = {}
def docked(t): return "MANTLE-DOCKED" in t.text()
def cmd(t, s):
    t.send(s); t.pump(0.6); t.send("\r"); t.pump(2.0)

# --- run 1: fresh home, nobody typed anything
t = Tui(home, 120, 30); res["1_autodock_no_user_action"] = t.wait_for("MANTLE-DOCKED", 150); t.pump(1)
print("run1 autodock:", res["1_autodock_no_user_action"], "| state:", state())
# dismiss = relaunch toggle
cmd(t, "/mantle"); res["1_dismissed_by_toggle"] = not docked(t)
print("run1 after /mantle toggle: docked =", docked(t), "| state:", state())
open(f"{out}/run1_after_toggle.txt", "w").write(t.text())
t.close()
# --- run 2: restart, must stay dismissed
t = Tui(home, 120, 30); t.pump(12)
res["2_stays_dismissed_after_restart"] = not docked(t)
print("run2 restart: docked =", docked(t), "| state:", state())
# re-enable
cmd(t, "/mantle"); res["2_reenable_by_command"] = docked(t)
print("run2 after /mantle: docked =", docked(t), "| state:", state())
t.close()
# --- run 3: restart => docked again (persisted 'on')
t = Tui(home, 120, 30); res["3_docked_after_reenable_restart"] = t.wait_for("MANTLE-DOCKED", 150)
print("run3 restart: docked =", res["3_docked_after_reenable_restart"], "| state:", state())
# explicit off command (no unmount involved)
cmd(t, "/mantle off"); print("run3 after /mantle off: docked =", docked(t), "| state:", state())
res["3_off_cmd_state_written"] = '"off"' in state()
t.close()
t = Tui(home, 120, 30); t.pump(12); res["4_stays_off_after_restart"] = not docked(t)
print("run4 restart after 'off': docked =", docked(t))
t.close()
# --- unclean exit (SIGKILL, no unmount) must NOT flip state
open(f"{home}/plugins/cuttlefish/state.json", "w").write('{"mantle":"on"}')
t = Tui(home, 120, 30); t.wait_for("MANTLE-DOCKED", 150); t.pump(1)
import signal; os.kill(t.pid, signal.SIGKILL); t.pump(1)
res["5_sigkill_leaves_state_on"] = '"on"' in state(); print("after SIGKILL state:", state())
t.close()
t = Tui(home, 120, 30); res["5_docked_after_sigkill"] = t.wait_for("MANTLE-DOCKED", 150); t.close()
# --- graceful exit (Ctrl-C x2 / /exit) : does unmount cleanup fire and wrongly persist 'dismissed'?
open(f"{home}/plugins/cuttlefish/state.json", "w").write('{"mantle":"on"}')
t = Tui(home, 120, 30); t.wait_for("MANTLE-DOCKED", 150); t.pump(1)
cmd(t, "/exit"); t.pump(3)
res["6_graceful_exit_state"] = state(); print("after graceful /exit state:", state())
t.close()
json.dump(res, open(f"{out}/results.json", "w"), indent=1); print(json.dumps(res, indent=1))
shutil.rmtree(home, ignore_errors=True)
