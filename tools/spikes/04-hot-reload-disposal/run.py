#!/usr/bin/env python3
"""Spike 04: hot-reload leak (fd + timer) and the Symbol-keyed disposer fix. One command: run.py [outdir]"""
import sys, os, json, shutil, time, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_lib"))
from tui import Tui, make_home
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-04"; os.makedirs(out, exist_ok=True)
N = 20

def node_pid(t):
    import subprocess
    r = subprocess.run(f"pstree -apl {t.pid}", shell=True, capture_output=True, text=True).stdout
    for line in r.splitlines():
        if "node-MainThread" in line or line.strip().split(",")[0].endswith("node"):
            return int(line.split(",")[1].split()[0])
    raise RuntimeError("no node pid:\n" + r)

def inotify_fds(pid):
    n = 0
    for fd in os.listdir(f"/proc/{pid}/fd"):
        try:
            if os.readlink(f"/proc/{pid}/fd/{fd}") == "anon_inode:inotify": n += 1
        except OSError: pass
    return n

def inotify_watches(pid):
    """total inotify watch descriptors across all inotify fds (each fs.watch => 1 watch)."""
    tot = 0
    for fd in os.listdir(f"/proc/{pid}/fd"):
        try:
            if os.readlink(f"/proc/{pid}/fd/{fd}") != "anon_inode:inotify": continue
            tot += sum(1 for l in open(f"/proc/{pid}/fdinfo/{fd}") if l.startswith("inotify wd:"))
        except OSError: pass
    return tot

def run(mode):
    home = make_home(); os.makedirs(f"{home}/watched")
    if mode == "dispose": open(f"{home}/mode-dispose", "w").write("1")
    shutil.copy(f"{HERE}/leaky.mjs", f"{home}/tui-widgets/leaky.mjs")
    t = Tui(home, 120, 30); assert t.wait_for("LEAKY", 200), "widget never mounted"; t.pump(3)
    pid = node_pid(t)
    base_w = inotify_watches(pid); base_fd = len(os.listdir(f"/proc/{pid}/fd"))
    series = [(0, inotify_watches(pid), len(os.listdir(f"/proc/{pid}/fd")))]
    tick = f"{home}/ticks.log"
    for i in range(1, N + 1):
        with open(f"{home}/tui-widgets/leaky.mjs", "a") as f: f.write(f"\n// touch {i}\n")   # triggers watchUserWidgets -> re-import
        time.sleep(1.0); t.pump(0.2)
        series.append((i, inotify_watches(pid), len(os.listdir(f"/proc/{pid}/fd"))))
    t.pump(1)
    # timers: count distinct ticker ids appending in a fresh 2s window
    mark = os.path.getsize(tick); time.sleep(2.0); t.pump(0.1)
    with open(tick) as f:
        f.seek(mark); ids = collections.Counter(f.read().split())
    cpu = None
    # live fs.watch handles: touch the watched dir, count DISTINCT watcher ids that fire
    wf = f"{home}/watch-fired.log"; open(wf, "w").close()
    open(f"{home}/watched/poke", "w").write("x"); time.sleep(1.5)
    live_watchers = len(set(open(wf).read().split()))
    res = {"mode": mode, "live_fs_watch_handles_firing": live_watchers, "node_pid": pid, "baseline_inotify_watches": base_w, "baseline_fds": base_fd,
           "series_reload_watches_fds": series, "final_watches": series[-1][1], "final_fds": series[-1][2],
           "live_timers_in_2s_window": len(ids), "ticks_per_timer": dict(ids)}
    t.close(); shutil.rmtree(home, ignore_errors=True)
    return res

results = {m: run(m) for m in ("leak", "dispose")}
json.dump(results, open(f"{out}/results.json", "w"), indent=1)
for m, r in results.items():
    print(f"[{m}] reload#: watches/fds ->", " ".join(f"{i}:{w}/{f}" for i, w, f in r["series_reload_watches_fds"][::4] + [r["series_reload_watches_fds"][-1]]))
    print(f"[{m}] baseline watches={r['baseline_inotify_watches']} final watches={r['final_watches']}  live timers={r['live_timers_in_2s_window']}  live fs.watch handles={r['live_fs_watch_handles_firing']}")
L, D = results["leak"], results["dispose"]
print("LEAK_PROVEN", L["live_fs_watch_handles_firing"] > 1 and L["final_watches"] > L["baseline_inotify_watches"] + N // 2 and L["live_timers_in_2s_window"] > 1)
print("FIX_PROVEN", D["final_watches"] <= D["baseline_inotify_watches"] + 2 and D["live_timers_in_2s_window"] == 1 and D["live_fs_watch_handles_firing"] == 1)
