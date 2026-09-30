#!/usr/bin/env python3
"""Spike 13 (G3): mantle repaint cost. One command: run.py [outdir]
(a) idle byte-silence + CPU when static; (b) keystroke->echo latency p50/p95, interleaved off/static/anim rounds;
(c) bytes/sec while animating.  Env: CF_FPS (default 6), CF_KEYS (per condition, default 240), CF_COLS (120),
CF_MAX_LOAD (1-min loadavg ceiling, default nproc/2), CF_MAX_PSI (CPU pressure-stall "some avg10" % ceiling, default
5.0 — the direct contention signal; loadavg alone counts idle-core-bound daemons), CF_SEED (jitter/bootstrap seed).

Measurement contract (settle.py): every idle control and every latency block starts only after the TUI reports
`ready` for SETTLE_NEED consecutive 1-s windows that are quiet (off/static) or steady (anim). A block that never
settles, loses `ready`, or runs on a loaded host marks the run `valid: false`, and an invalid run emits NO verdict
inputs. Exit code: 0 valid, 3 invalid (data is still written for inspection)."""
import sys, os, json, shutil, time, random, statistics, subprocess, select
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "_lib")); sys.path.insert(0, os.path.join(HERE, "..", "..", "capture"))
from tui import Tui, make_home
from pty_to_png import render_png
import settle as S
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cf-spike-13"; os.makedirs(out, exist_ok=True)
KEYS = int(os.environ.get("CF_KEYS", 240)); COLS = int(os.environ.get("CF_COLS", 120)); ROUNDS = 4
MAX_LOAD = float(os.environ.get("CF_MAX_LOAD", os.cpu_count() / 2)); MAX_PSI = float(os.environ.get("CF_MAX_PSI", 5.0)); SEED = int(os.environ.get("CF_SEED", time.time_ns() % 2**31))
random.seed(SEED)
home = make_home(); shutil.copy(f"{HERE}/mantle.mjs", f"{home}/tui-widgets/mantle13.mjs")
setmode = lambda m: open(f"{home}/mantle-mode", "w").write(m)
setmode("static")                       # boot at rest: startup is observed settling with the mantle on screen
t = Tui(home, COLS, 40)
assert t.wait_for("▀", 200), "mantle never rendered"
problems, trace = [], []                # trace = every settle window, kept for post-mortem of invalid runs

def node_pid():
    r = subprocess.run(f"pstree -apl {t.pid}", shell=True, capture_output=True, text=True).stdout
    for line in r.splitlines():
        if "node-MainThread" in line.split(",")[0] or "node," in line.split(" ")[0]:
            return int(line.split(",")[1].split()[0])
NODE = node_pid()
def cpu_ticks(pid):
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split(); return int(f[11]) + int(f[12])
HZ = os.sysconf("SC_CLK_TCK")
status = lambda: S.status_of(t.screen.display)
def cpu_psi():
    try: return float(open("/proc/pressure/cpu").read().split()[1].split("=")[1])   # "some avg10=X"
    except (OSError, ValueError, IndexError): return None             # no PSI (old kernel/container): loadavg still gates
def host_problems(tag):
    la, ps = os.getloadavg()[0], cpu_psi(); why = []
    if la > MAX_LOAD: why.append(f"{tag}: loadavg {la:.2f} > {MAX_LOAD}")
    if ps is not None and ps > MAX_PSI: why.append(f"{tag}: cpu psi avg10 {ps:.2f}% > {MAX_PSI}%")
    return la, ps, why

MODE_NOW = "static"
def wait_settled(label, limit=240):
    """1-s windows until SETTLE_NEED consecutive ones are ready + quiet (steady for anim), else unsettled."""
    wins, t0 = [], time.time()
    while time.time() - t0 < limit:
        t.raw.clear(); w0 = time.time(); t.pump(S.SETTLE_WINDOW_S)
        wins.append({"bytes": len(t.raw), "secs": round(time.time() - w0, 3), "status": status()})
        if S.settled_index(wins, anim=(MODE_NOW == "anim")) is not None:
            trace.append({"at": label, "mode": MODE_NOW, "windows": wins})
            return {"settled": True, "settle_s": round(time.time() - t0, 1), "settle_windows": len(wins)}
    trace.append({"at": label, "mode": MODE_NOW, "windows": wins})
    return {"settled": False, "settle_s": round(time.time() - t0, 1), "settle_windows": len(wins),
            "settle_reason": f"no {S.SETTLE_NEED}-window ready+{'steady' if MODE_NOW == 'anim' else 'quiet'} streak in {limit}s"}

def set_mode(m):
    global MODE_NOW; MODE_NOW = m
    setmode(m); t.resize(COLS + 1, 40); t.pump(0.8); t.resize(COLS, 40); t.pump(1.0)   # widget reads mode on render

def measure_idle(secs=10):
    s = wait_settled(f"idle-{MODE_NOW}")
    st0 = status(); t.raw.clear(); c0 = cpu_ticks(NODE); w0 = time.time()
    t.pump(secs); dt = time.time() - w0
    idle = {**s, "status_start": st0, "status_end": status(), "bytes": len(t.raw), "bytes_per_s": len(t.raw) / dt,
            "node_cpu_pct": 100 * (cpu_ticks(NODE) - c0) / HZ / dt}
    idle["loadavg"], idle["cpu_psi_avg10"], hw = host_problems(f"idle {MODE_NOW}")
    idle["problems"] = S.validate_idle(idle, MODE_NOW) + hw; problems.extend(idle["problems"])
    return idle

def latency(n):
    lat = []
    for i in range(n):
        t.pump(random.uniform(0.03, 0.09))          # jitter: never phase-locked to the animation
        t0 = time.perf_counter(); t.send("z")
        while True:
            left = 2.0 - (time.perf_counter() - t0)          # hard 2 s deadline: echo that never lands = MISS
            if left <= 0: lat.append(None); break
            r, _, _ = select.select([t.fd], [], [], left)
            if not r: lat.append(None); break
            d = os.read(t.fd, 65536); t.raw += d; t.stream.feed(d)
            if b"z" in d: lat.append((time.perf_counter() - t0) * 1000); break
        t.send("\x7f"); t.pump(0.02)
    return lat

res = {"conditions": {}, "meta": {"fps": os.environ.get("CF_FPS", "6"), "quant": os.environ.get("CF_QUANT", "0"),
       "memo": os.environ.get("CF_MEMO", "0"), "rle": os.environ.get("CF_RLE", "0"), "cols": COLS,
       "keys_per_condition": KEYS, "rounds": ROUNDS, "seed": SEED, "max_load": MAX_LOAD, "max_psi": MAX_PSI, "nproc": os.cpu_count(), "loadavg_start": os.getloadavg(),
       "contract": {"settle_window_s": S.SETTLE_WINDOW_S, "settle_need": S.SETTLE_NEED, "max_idle_bps": S.MAX_IDLE_BPS,
                    "anim_steady_ratio": S.ANIM_STEADY_RATIO, "g3_budget_ms": S.G3_BUDGET_MS}}}
problems.extend(host_problems("host at start")[2])
boot = wait_settled("boot"); res["meta"]["boot_settle"] = boot
if not boot["settled"]: problems.append(f"boot: {boot['settle_reason']}")
order = ["off", "static", "anim"]
for m in order:
    set_mode(m); res["conditions"][m] = {"idle": measure_idle(10)}
    print(m, "idle", res["conditions"][m]["idle"], flush=True)
    if m == "anim":
        render_png(t.screen, f"{out}/13-mantle-anim-{COLS}.png")
        open(f"{out}/anim-frame-bytes.bin", "wb").write(bytes(t.raw[-4000:]))
# interleaved latency rounds; each block is gated exactly like an idle control
lat = {m: [] for m in order}; rounds = []; per = KEYS // ROUNDS
for r in range(ROUNDS):
    row = {"round": r, "order": order if r % 2 == 0 else order[::-1], "p95": {}, "p50": {}, "blocks": {}}
    for m in row["order"]:
        set_mode(m); s = wait_settled(f"lat-r{r}-{m}"); st0 = status()
        xs = latency(per); lat[m] += xs; ok = [x for x in xs if x is not None]
        la, ps, hw = host_problems(f"lat r{r} {m}")
        blk = {**s, "status_start": st0, "status_end": status(), "loadavg": la, "cpu_psi_avg10": ps, "missed": len(xs) - len(ok)}
        why = [f"lat r{r} {w}" for w in S.validate_block(blk, m)] + hw
        blk["problems"] = why; problems.extend(why); row["blocks"][m] = blk
        row["p95"][m] = S.pctl(ok, .95) if ok else None; row["p50"][m] = S.pctl(ok, .5) if ok else None
    for c in ("anim", "static"):
        row[f"{c}_minus_off_p95"] = None if None in (row["p95"][c], row["p95"]["off"]) else row["p95"][c] - row["p95"]["off"]
    rounds.append(row); print("round", r, {k: row[k] for k in ("p95", "anim_minus_off_p95", "static_minus_off_p95")}, flush=True)
res["rounds"] = rounds
for m in order:
    xs = sorted(x for x in lat[m] if x is not None); miss = sum(x is None for x in lat[m])
    res["conditions"][m]["latency_ms"] = ({"n": len(xs), "missed": miss, "p50": S.pctl(xs, .5), "p95": S.pctl(xs, .95),
                                           "p99": S.pctl(xs, .99), "max": xs[-1], "mean": statistics.mean(xs)} if xs else {"n": 0, "missed": miss})
    if len(xs) < per * ROUNDS - 1: problems.append(f"{m}: only {len(xs)}/{per * ROUNDS} echoes landed")
    print(m, res["conditions"][m]["latency_ms"], flush=True)
res["meta"]["loadavg_end"] = os.getloadavg(); res["meta"]["cpu_psi_end"] = cpu_psi()
problems.extend(host_problems("host at end")[2])
res["valid"] = not problems; res["problems"] = problems
if res["valid"]:
    ok = {m: [x for x in lat[m] if x is not None] for m in order}
    ci_a = S.bootstrap_delta_ci(ok["off"], ok["anim"], seed=SEED); ci_s = S.bootstrap_delta_ci(ok["off"], ok["static"], seed=SEED)
    lm = {m: res["conditions"][m]["latency_ms"] for m in order}
    d_rounds = [r["anim_minus_off_p95"] for r in rounds]
    res["verdict_inputs"] = {
        "p95_off": lm["off"]["p95"], "p95_static": lm["static"]["p95"], "p95_anim": lm["anim"]["p95"],
        "anim_minus_off_p95_ms": lm["anim"]["p95"] - lm["off"]["p95"], "anim_minus_off_p95_ci95": ci_a,
        "static_minus_off_p95_ms": lm["static"]["p95"] - lm["off"]["p95"], "static_minus_off_p95_ci95": ci_s,
        "per_round_anim_minus_off_p95": d_rounds, "per_round_spread_ms": max(d_rounds) - min(d_rounds),
        "g3_run_class": S.classify_run(ci_a), "g3_static_run_class": S.classify_run(ci_s),
        "static_idle_bytes": res["conditions"]["static"]["idle"]["bytes"], "static_idle_cpu_pct": res["conditions"]["static"]["idle"]["node_cpu_pct"],
        "off_idle_bytes": res["conditions"]["off"]["idle"]["bytes"], "off_idle_cpu_pct": res["conditions"]["off"]["idle"]["node_cpu_pct"],
        "anim_bytes_per_s": res["conditions"]["anim"]["idle"]["bytes_per_s"], "anim_cpu_pct": res["conditions"]["anim"]["idle"]["node_cpu_pct"]}
json.dump(res, open(f"{out}/results.json", "w"), indent=1); json.dump(lat, open(f"{out}/latency-raw.json", "w"))
json.dump(trace, open(f"{out}/settle-trace.json", "w"))
print(json.dumps(res.get("verdict_inputs") or {"valid": False, "problems": problems}, indent=1))
t.close(); shutil.rmtree(home, ignore_errors=True)
sys.exit(0 if res["valid"] else 3)
