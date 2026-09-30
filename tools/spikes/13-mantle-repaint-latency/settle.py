"""Spike 13 measurement contract: pure functions, no pty (unit-tested in tools/tests/test_spike13_settle.py).

Why this exists: the first harness called the TUI "quiet" after ANY single 3-s window under 200 bytes. A short
lull in the startup spinner satisfied that, so an "idle" control could still be measuring `starting agent…`
(840 B/s) or a repaint storm (3,249 B/s, 24 % CPU) and the run was scored anyway. The rules here:

  * settled  = `need` CONSECUTIVE windows, each with status `ready` AND a byte rate at or below `max_bps`;
  * an idle control is valid only if it starts and ends `ready` and its own byte rate is at or below `max_bps`
    (the anim control is exempt from the byte rule: animating is the thing being measured);
  * a run with any invalid control is NOT scored: it carries `valid: false` + reasons, never verdict inputs;
  * the G3 decision is per-run bootstrap CI on the interleaved anim−off p95 delta, pass/fail/indeterminate
    against the unchanged +2 ms bar.
"""
from __future__ import annotations

import random
import re

# The stock host writes ~45 B/s at rest (status-bar uptime counter); a 1-s window holding one clock tick is
# ~45-60 B. 120 B/s is ~2.5x that and ~7x below the contaminated startup control (840 B/s).
MAX_IDLE_BPS = 120.0
SETTLE_WINDOW_S = 1.0
SETTLE_NEED = 3
G3_BUDGET_MS = 2.0

_STATUS = re.compile(r"^\W*(ready|starting agent|starting|working|thinking|error|connecting)\b", re.I)


def status_of(display_lines) -> str | None:
    """The TUI status bar starts with `─ <state> │ <model> │ ...`. Return the state word ('ready',
    'starting agent', ...) or None when no status bar is on screen (e.g. mid-repaint)."""
    for line in display_lines:
        if "│" not in line:
            continue
        m = _STATUS.match(line.strip())
        if m:
            return m.group(1).lower()
    return None


ANIM_STEADY_RATIO = 1.5   # anim streak: max/min window bytes within 1.5x (frames only, no startup/resize burst)


def legacy_quiet(chunk_bytes: int) -> bool:
    """The ORIGINAL detector (run.py@65c9656 wait_quiet): one 3-s chunk under 200 bytes == quiet. Kept only so
    the regression test can prove it accepts the contaminated startup sequence the new contract rejects."""
    return chunk_bytes < 200


def _rate(w):
    return w["bytes"] / max(w["secs"], 1e-9)


def settled_index(windows, need=SETTLE_NEED, max_bps=MAX_IDLE_BPS, anim=False):
    """windows: list of {'bytes', 'secs', 'status'} in time order. Return the index of the window that
    completes the first run of `need` consecutive settled windows, else None.
    Settled = status 'ready' AND (off/static) rate <= max_bps, or (anim) rate within ANIM_STEADY_RATIO of
    every other window in the streak — the animation is allowed to write, a startup burst is not."""
    for end in range(need - 1, len(windows)):
        run = windows[end - need + 1:end + 1]
        if any(w.get("status") != "ready" for w in run):
            continue
        rates = [_rate(w) for w in run]
        if anim:
            if min(rates) > 0 and max(rates) / min(rates) <= ANIM_STEADY_RATIO:
                return end
        elif max(rates) <= max_bps:
            return end
    return None


def validate_block(blk: dict, mode: str) -> list[str]:
    """Reasons a measurement block (idle control or latency block) must not be scored. Empty = valid."""
    why = []
    if not blk.get("settled"):
        why.append(f"{mode}: never settled ({blk.get('settle_reason', 'no settled streak')})")
    for edge in ("status_start", "status_end"):
        if blk.get(edge) != "ready":
            why.append(f"{mode}: {edge}={blk.get(edge)!r}, not 'ready'")
    return why


def validate_idle(idle: dict, mode: str, max_bps=MAX_IDLE_BPS) -> list[str]:
    """validate_block + the at-rest byte ceiling for off/static (anim is exempt: its bytes are the measurement)."""
    why = validate_block(idle, mode)
    if mode != "anim" and idle.get("bytes_per_s", 0) > max_bps:
        why.append(f"{mode}: idle {idle['bytes_per_s']:.1f} B/s > {max_bps} B/s (not at rest)")
    return why


def pctl(xs, p):
    """Same index rule the original receipt used (kept for comparability with the preserved raw runs)."""
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def bootstrap_delta_ci(a, b, p=0.95, n=2000, seed=13, alpha=0.05):
    """Percentile-bootstrap CI of pctl(b,p) - pctl(a,p), resampling each condition independently."""
    rng = random.Random(seed)
    ds = sorted(pctl(rng.choices(b, k=len(b)), p) - pctl(rng.choices(a, k=len(a)), p) for _ in range(n))
    return ds[int(alpha / 2 * n)], ds[min(n - 1, int((1 - alpha / 2) * n))]


def pooled_delta_ci(pairs, p=0.95, n=2000, seed=13, alpha=0.05):
    """Secondary evidence only: stratified bootstrap over runs. pairs = [(off_samples, cond_samples), ...];
    each replicate resamples within every run, pools, and takes pctl(pooled cond) - pctl(pooled off).
    Not used by classify_gate (runs differ in host state; the gate stays per-run + unanimous)."""
    rng = random.Random(seed)
    ds = []
    for _ in range(n):
        a, b = [], []
        for off, cond in pairs:
            a += rng.choices(off, k=len(off)); b += rng.choices(cond, k=len(cond))
        ds.append(pctl(b, p) - pctl(a, p))
    ds.sort()
    return ds[int(alpha / 2 * n)], ds[min(n - 1, int((1 - alpha / 2) * n))]


def classify_run(ci, budget=G3_BUDGET_MS) -> str:
    lo, hi = ci
    if hi <= budget:
        return "pass"
    if lo > budget:
        return "fail"
    return "indeterminate"


def classify_gate(run_classes, min_runs=3) -> str:
    """Gate verdict over valid runs: pass/fail only when >= min_runs valid runs ALL agree; otherwise
    indeterminate. Unanimity is deliberate — one run is exactly the evidence the review showed can flip."""
    if len(run_classes) < min_runs:
        return "indeterminate"
    if all(c == "pass" for c in run_classes):
        return "pass"
    if all(c == "fail" for c in run_classes):
        return "fail"
    return "indeterminate"
