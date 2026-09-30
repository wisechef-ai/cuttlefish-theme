#!/usr/bin/env python3
"""Spike 13 (G3): mantle repaint cost. One command: run.py [outdir]
(a) idle byte-silence + CPU when static; (b) keystroke->echo latency p50/p95, interleaved off/static/anim rounds;
(c) bytes/sec while animating.  Env: CF_FPS (default 6), CF_KEYS (per condition, default 240), CF_COLS (120)."""
import sys, os, json, shutil, time, random, statistics, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_lib")); sys.path.insert(0, os.path.join(HERE, "..", "..", "capture"))
from tui import Tui, make_home
from pty_to_png import render_png
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-13"; os.makedirs(out, exist_ok=True)
KEYS = int(os.environ.get("CF_KEYS", 240)); COLS = int(os.environ.get("CF_COLS", 120)); ROUNDS = 4
home = make_home(); shutil.copy(f"{HERE}/mantle.mjs", f"{home}/tui-widgets/mantle13.mjs")
setmode = lambda m: open(f"{home}/mantle-mode", "w").write(m)
setmode("anim")
t = Tui(home, COLS, 40)
assert t.wait_for("▀", 200), "mantle never rendered"; t.pump(3)

def node_pid():
    r = subprocess.run(f"pstree -apl {t.pid}", shell=True, capture_output=True, text=True).stdout
    for line in r.splitlines():
        if "node-MainThread" in line.split(",")[0] or "node," in line.split(" ")[0]:
            return int(line.split(",")[1].split()[0])
NODE = node_pid()
def cpu_ticks(pid):
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split(); return int(f[11]) + int(f[12])
HZ = os.sysconf("SC_CLK_TCK")

MODE_NOW = "anim"
def set_and_settle(m):
    global MODE_NOW; MODE_NOW = m
    setmode(m); t.resize(COLS + 1, 40); t.pump(0.8); t.resize(COLS, 40); t.pump(2.0)   # widget reads mode on render

def wait_quiet(limit=180):
    """TUI startup (gateway 'starting…' spinner) animates on its own; idle numbers are only meaningful after it ends."""
    t0 = time.time()
    while time.time() - t0 < limit:
        t.raw.clear(); t.pump(3.0)
        if len(t.raw) < 200: return round(time.time() - t0, 1)
    return None

def measure_idle(secs=10):
    waited = wait_quiet() if MODE_NOW != "anim" else 0
    t.raw.clear(); c0 = cpu_ticks(NODE); w0 = time.time()
    t.pump(secs); dt = time.time() - w0
    return {"quiet_wait_s": waited, "status_line": [l.strip() for l in t.screen.display if "starting" in l or "ready" in l][:2], "bytes": len(t.raw), "bytes_per_s": len(t.raw) / dt, "node_cpu_pct": 100 * (cpu_ticks(NODE) - c0) / HZ / dt}

def latency(n):
    lat = []
    for i in range(n):
        t.pump(random.uniform(0.03, 0.09))          # jitter: never phase-locked to the animation
        mark = len(t.raw); t0 = time.perf_counter(); t.send("z")
        import select
        while True:
            left = 2.0 - (time.perf_counter() - t0)          # hard 2 s deadline: echo that never lands = MISS
            if left <= 0: lat.append(None); break
            r, _, _ = select.select([t.fd], [], [], left)
            if not r: lat.append(None); break
            d = os.read(t.fd, 65536); t.raw += d; t.stream.feed(d)
            if b"z" in d: lat.append((time.perf_counter() - t0) * 1000); break
        t.send("\x7f"); t.pump(0.02)
    return lat

res = {"conditions": {}, "meta": {"fps": os.environ.get("CF_FPS", "6"), "cols": COLS, "keys_per_condition": KEYS * 1,
                                   "loadavg_start": os.getloadavg()}}
lat = {"off": [], "static": [], "anim": []}
per = KEYS // ROUNDS
order = ["off", "static", "anim"]
# idle first (proper settle each)
for m in order:
    set_and_settle(m); res["conditions"][m] = {"idle": measure_idle(10)}
    print(m, "idle", res["conditions"][m]["idle"], flush=True)
    if m == "anim":
        render_png(t.screen, f"{out}/13-mantle-anim-{COLS}.png")
        open(f"{out}/anim-frame-bytes.bin", "wb").write(bytes(t.raw[-4000:]))
# interleaved latency rounds
for r in range(ROUNDS):
    for m in (order if r % 2 == 0 else order[::-1]):
        set_and_settle(m); lat[m] += latency(per)
for m in order:
    xs = sorted(x for x in lat[m] if x is not None); miss = sum(x is None for x in lat[m])
    q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]
    res["conditions"][m]["latency_ms"] = {"n": len(xs), "missed": miss, "p50": q(.5), "p95": q(.95), "p99": q(.99), "max": xs[-1], "mean": statistics.mean(xs)}
    print(m, res["conditions"][m]["latency_ms"], flush=True)
base = res["conditions"]["off"]["latency_ms"]["p95"]
res["verdict_inputs"] = {"p95_off": base, "p95_static": res["conditions"]["static"]["latency_ms"]["p95"], "p95_anim": res["conditions"]["anim"]["latency_ms"]["p95"],
                        "anim_minus_off_p95_ms": res["conditions"]["anim"]["latency_ms"]["p95"] - base,
                        "static_idle_bytes": res["conditions"]["static"]["idle"]["bytes"], "static_idle_cpu_pct": res["conditions"]["static"]["idle"]["node_cpu_pct"]}
res["meta"]["loadavg_end"] = os.getloadavg()
json.dump(res, open(f"{out}/results.json", "w"), indent=1); json.dump(lat, open(f"{out}/latency-raw.json", "w"))
print(json.dumps(res["verdict_inputs"], indent=1))
t.close(); shutil.rmtree(home, ignore_errors=True)
