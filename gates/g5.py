#!/usr/bin/env python3
"""G5: blind vision gate (tools/p1/CONTRACT.md section 5). Two independent vision backends, fixed prompts, no design context.

    gates/.venv/bin/python gates/g5.py <manifest.json> [--backends qwen,glm] [--seed 2909] [--workers 4]

Exit 0 = PASS (every backend passes every task), 1 = FAIL, 2 = instrument error, 3 = partial run (--tasks subset) with no failure. Writes g5.json + g5.md next to the manifest, every
raw model response under g5_raw/<backend>/, and appends the run to gates/g5_rounds.json (the kill-rule counter).
Only renders from the manifest, the synthetic/public fixtures and the openly licensed photos in gates/photos/ are sent.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dirtools as dt  # noqa: E402
import g5backends  # noqa: E402
import g5cache  # noqa: E402
import g5items  # noqa: E402
import g5lib  # noqa: E402
import gatelib as gl  # noqa: E402

ROUNDS_FILE = Path(__file__).resolve().parent / "g5_rounds.json"
ANCHOR_MEDIAN_MIN = g5lib.AESTHETIC_MEDIAN_MIN


def ask(backend_fn, item: g5items.Item, png: Path, attempts: int = 5) -> dict:
    """One blind call. Transport errors are retried (backends that retry internally get one attempt here, so the budgets do not
    multiply); an unparseable answer is NOT retried (it is a FAIL for the item)."""
    if getattr(backend_fn, "retries_internal", False):
        attempts = 1
    err, raw = "", ""
    for k in range(attempts):
        try:
            raw = backend_fn(png, item.prompt)
            err = ""
            break
        except Exception as e:  # noqa: BLE001: any transport failure is recorded, then retried
            err = f"{type(e).__name__}: {e}"[:400]
            time.sleep((20 if "429" in err else 2) * (k + 1))
    ans = g5lib.parse_answer(raw, item.task) if not err else g5lib.Answer(False, None, err)
    return {"cached": bool(getattr(backend_fn, "last_cached", False)) and not err, "id": item.id, "kind": item.kind, "family": item.family, "variant": item.variant, "truth": item.truth, "source": item.source,
            "raw": raw, "transport_error": err, "valid": ans.valid, "value": ans.value, "parse_error": ans.error}


def run_backend(name: str, fn, items: list[g5items.Item], pngs: dict, raw_dir: Path, workers: int) -> list[dict]:
    out_dir = raw_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(item):
        r = ask(fn, item, pngs[item.id])
        (out_dir / f"{item.id}.json").write_text(json.dumps({**r, "prompt_file": item.prompt_file, "prompt": item.prompt, "image": pngs[item.id].name}, indent=1))
        return r

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, items))


def score_backend(results: list[dict], tasks=g5items.TASKS) -> dict:
    aes = [r for r in results if r["kind"] == "aesthetic"]
    direction = [r["value"] if r["valid"] else None for r in aes if r["family"] != "photo"]
    photos = [r["value"] if r["valid"] else None for r in aes if r["family"] == "photo"]
    aes_v = g5lib.aesthetic_verdict(direction)
    by_family = {f: statistics.median([r["value"] for r in aes if r["family"] == f and r["valid"]])
                 for f in ("XL", "M", "S") if any(r["family"] == f and r["valid"] for r in aes)}
    good_photos = [p for p in photos if p is not None]
    anchor_med = statistics.median(good_photos) if good_photos else None
    anchor_ok = bool(photos) and len(good_photos) == len(photos) and (anchor_med or 0) >= ANCHOR_MEDIAN_MIN

    def legend(variant):
        rs = [r for r in results if r["kind"] == "legend" and r["variant"] == variant]
        pairs = [(r["truth"], r["value"] if r["valid"] else None) for r in rs]
        return {**g5lib.legend_verdict(pairs), "confusion": g5lib.confusion_matrix(pairs)}

    plain = legend("plain")
    cvd = {k: legend(k) for k in gl.CVD_KINDS}
    ids = sorted([r for r in results if r["kind"] == "identity"], key=lambda r: r["id"])
    ident = (g5lib.identity_verdict([r["value"] if r["valid"] else None for r in ids], [r["truth"] for r in ids])
             if ids else {"pass": False, "correct": 0, "n": 0, "invalid": 0})
    checks = {"aesthetic": aes_v["pass"], "anchor_floor": anchor_ok, "legend": plain["pass"],
              **{f"cvd_{k}": v["pass"] for k, v in cvd.items()}, "identity": ident["pass"]}
    keep = {"aesthetic": ("aesthetic", "anchor_floor"), "legend": ("legend", *[f"cvd_{k}" for k in cvd]), "identity": ("identity",)}
    checks = {k: v for t in tasks for k, v in checks.items() if k in keep[t]}
    return {"pass": all(checks.values()), "checks": checks,
            "aesthetic": {**aes_v, "median_by_family": by_family,
                          "scores": {r["id"]: (r["value"] if r["valid"] else None) for r in aes if r["family"] != "photo"}},
            "anchor_photos": {"median": anchor_med, "scores": photos, "floor": ANCHOR_MEDIAN_MIN, "ok": anchor_ok},
            "legend": plain, "cvd": cvd, "identity": ident,
            "invalid_or_failed_calls": sum(1 for r in results if not r["valid"]), "calls": len(results)}


def text_policy(keep_alarm_text) -> str:
    return {None: "default (D-R2-5): plain legend keeps alarm words, CVD legends + identity mask all text",
            True: "OVERRIDE keep-alarm-text: alarm words visible in every legend variant (informational run, not the gate)",
            False: "OVERRIDE mask-all-text: no text in any legend variant (informational run, not the gate)"}[keep_alarm_text]


def to_markdown(rep: dict) -> str:
    L = [f'# G5: {rep["direction"]}: {"PASS" if rep["pass"] else "FAIL"}', "",
         f'Seed {rep["seed"]}; tasks {",".join(rep["tasks"])}' + (' (**PARTIAL run, no gate verdict**)' if rep["partial"] else '') + f'; {rep["items"]} blind items per backend' + (f' (**SAMPLED run: at most {rep["sampled_per_cell"]} per cell, not the full gate**)' if rep.get("sampled_per_cell") else '') + '; backends: ' + ", ".join(f'`{b}` ({rep["models"][b]})' for b in rep["backends"]), ""]
    L += [f'Text policy: {text_policy(rep["keep_alarm_text"])}.', ""]
    ca = rep.get("cache", {})
    if ca:
        L += ["Answer cache: " + ", ".join(f"`{b}` {c['cached']}/{c['calls']} answers served from cache" for b, c in ca.items()) + (" (cache disabled)" if not rep.get("cache_enabled", True) else "") + ".", ""]
    for b, s in rep["per_backend"].items():
        a, lg = s["aesthetic"], s["legend"]
        L += [f"## Backend `{b}`: {'PASS' if s['pass'] else 'FAIL'}", "",
              "- checks: " + ", ".join(f'{k}={"ok" if v else "**FAIL**"}' for k, v in s["checks"].items()),
              f'- aesthetic (need median >= 7, none < 6): median {a["median"]}, min {a["min"]}, n {a["n"]}, invalid {a["invalid"]}; by scale {a["median_by_family"]}',
              f'- anchor real-animal photos (sanity floor >= {s["anchor_photos"]["floor"]}): median {s["anchor_photos"]["median"]}, scores {s["anchor_photos"]["scores"]}',
              f'- legend naming (need >= 80 %, INPUT<->ERROR = 0): {lg["correct"]}/{lg["n"]} = {lg["accuracy"]:.0%}, INPUT<->ERROR confusions **{lg["input_error_confusions"]}**, invalid {lg["invalid"]}']
        L += [f'- CVD {k} legend: {v["correct"]}/{v["n"]} = {v["accuracy"]:.0%}, INPUT<->ERROR **{v["input_error_confusions"]}** -> {"ok" if v["pass"] else "**FAIL**"}' for k, v in s["cvd"].items()]
        L += [f'- identity matching (need >= 14/16): **{s["identity"]["correct"]}/{s["identity"]["n"]}**, invalid {s["identity"]["invalid"]}', "",
              "Legend confusion matrix:", "", g5lib.confusion_markdown(lg["confusion"]), ""]
        for k, v in s["cvd"].items():
            L += [f"CVD {k} confusion matrix:", "", g5lib.confusion_markdown(v["confusion"]), ""]
    if rep.get("round"):
        r = rep["round"]
        L += ["## Kill-rule counter", f'- consecutive failing G5 rounds for `{rep["direction"]}`: {r["consecutive_failing_rounds"]}'
              + (" **KILL RULE TRIGGERED: stop and re-grill (lead's call)**" if r["kill_rule_triggered"] else "")]
    return "\n".join(L) + "\n"


def run(manifest_path, backends: dict, seed: int = 2909, workers: int = 4, direction_dir_hint=None, rounds_file: Path | None = ROUNDS_FILE, limit=None,
        sample: int | None = None, tasks=g5items.TASKS, keep_alarm_text: bool | None = None, cache: g5cache.Cache | None = None) -> dict:
    man = gl.load_manifest(manifest_path)
    ddir = dt.resolve_direction_dir(man.direction, direction_dir_hint)
    items = g5items.build_items(man, ddir, seed, tasks, keep_alarm_text)
    if not items:
        raise RuntimeError("manifest produced no G5 items")
    items = g5lib.seeded_shuffle(items, seed)
    if sample:
        items = g5lib.sample_per_cell(items, sample, lambda i: (i.kind, i.family, i.variant), lambda i: i.truth)
    items = items[: limit or None]
    raw_dir = man.root / "g5_raw"
    img_dir = raw_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    pngs = {}
    for it in items:
        pngs[it.id] = img_dir / f"{it.id}.png"
        it.image.save(pngs[it.id])
    per, cache_stats = {}, {}
    for name, fn in backends.items():
        if cache is not None:
            fn = g5cache.cached(fn, name, g5backends.cache_model(name), cache)
        results = run_backend(name, fn, items, pngs, raw_dir, workers)
        cache_stats[name] = {"cached": sum(1 for r in results if r["cached"]), "calls": len(results)}
        per[name] = score_backend(results, tasks)
    rep = {"schema": "cf2909.p1.g5/1", "direction": man.direction, "manifest": str(man.path), "seed": seed, "items": len(items),
           "backends": list(backends), "models": {b: g5backends.label(b) for b in backends}, "per_backend": per,
           "pass": all(s["pass"] for s in per.values()), "synthetic": bool(man.raw.get("synthetic")), "sampled_per_cell": sample,
           "keep_alarm_text": keep_alarm_text, "cache": cache_stats, "cache_enabled": bool(cache and cache.enabled), "tasks": list(tasks), "partial": tuple(tasks) != g5items.TASKS}
    if rounds_file is not None:
        rep["round"] = g5lib.record_round(rounds_file, man.direction, rep["pass"], backends=list(backends), seed=seed,
                                          manifest=str(man.path), synthetic=rep["synthetic"])
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("--backends", default=g5backends.DEFAULT_BACKENDS)
    ap.add_argument("--seed", type=int, default=2909)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--direction-dir")
    ap.add_argument("--rounds-file", default=str(ROUNDS_FILE))
    ap.add_argument("--no-round", action="store_true", help="do not append to the kill-rule counter")
    ap.add_argument("--sample", type=int, help="cost cap: at most N items per (task, scale, variant) cell, labels round-robin. Recorded in the report; the full gate runs without it")
    ap.add_argument("--tasks", default=",".join(g5items.TASKS), help="subset of aesthetic,legend,identity; a subset can FAIL but never PASS the gate")
    ap.add_argument("--keep-alarm-text", action="store_true", help="INFORMATIONAL override: keep alarm words visible in every legend variant, CVD included (default D-R2-5: plain keeps them, CVD masks all)")
    ap.add_argument("--mask-alarm-text", action="store_true", help="INFORMATIONAL override: mask all text in every legend variant, plain included")
    ap.add_argument("--no-cache", action="store_true", help="ignore and do not write the raw-answer cache (default: answers are cached by backend, model, image and prompt hash)")
    ap.add_argument("--cache-dir", default=str(g5cache.DEFAULT_DIR))
    ap.add_argument("--limit", type=int, help="debug: only the first N shuffled items (never a gate result)")
    a = ap.parse_args(argv)
    if a.keep_alarm_text and a.mask_alarm_text:
        print("--keep-alarm-text and --mask-alarm-text are mutually exclusive", file=sys.stderr)
        return 2
    names = [n.strip() for n in a.backends.split(",") if n.strip()]
    if len(set(names)) < 2 or any(g5backends.resolve(n) is None for n in names):
        print(f"G5 needs two distinct backends: qwen, glm, codex, gemini:<model>, openrouter[:<vendor/model>]; got {names}", file=sys.stderr)
        return 2
    try:
        rep = run(a.manifest, {n: g5backends.resolve(n) for n in names}, a.seed, a.workers, a.direction_dir,
                  None if a.no_round else Path(a.rounds_file), a.limit, a.sample, tuple(t for t in a.tasks.split(",") if t),
                  True if a.keep_alarm_text else False if a.mask_alarm_text else None, g5cache.Cache(Path(a.cache_dir), enabled=not a.no_cache))
    except (gl.ManifestError, dt.DirectionError, RuntimeError, FileNotFoundError) as e:
        print(f"G5 instrument error: {e}", file=sys.stderr)
        return 2
    root = Path(a.manifest).resolve().parent
    (root / "g5.json").write_text(json.dumps(rep, indent=2, default=str))
    (root / "g5.md").write_text(to_markdown(rep))
    partial = rep["partial"] and rep["pass"]   # a partial run proves nothing about the tasks it skipped
    verdicts = "; ".join(f'{b}={"pass" if s["pass"] else "fail:" + ",".join(k for k, v in s["checks"].items() if not v)}' for b, s in rep["per_backend"].items())
    print(f'G5 {"PARTIAL (no verdict: tasks " + ",".join(rep["tasks"]) + " ok)" if partial else "PASS" if rep["pass"] else "FAIL"} {rep["direction"]}: {verdicts}')
    return 3 if partial else 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
