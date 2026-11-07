#!/usr/bin/env python3
"""Recompute every number of the evidence manifest from the RAW files, with the contract's own instruments (dev only).

    python3 tools/desktop/measure.py <evidence-dir>      # <evidence-dir>/raw/... → JSON on stdout

Uses tests/acceptance/instruments_py.py (pixel maths, pinned to the O2 instruments) and raw_evidence.py (CSV loaders and
summaries) exactly as test_o7_part1_recompute.py does, so a number written into the manifest is the number the test recomputes.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ACCEPT = Path(__file__).resolve().parents[2] / "tests" / "acceptance"
CPU_FILES = {"idle_on": "cpu/idle.on.csv", "idle_off": "cpu/idle.off.csv",
             "working_on": "cpu/working.on.csv", "working_off": "cpu/working.off.csv"}


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"_cf_{name}", ACCEPT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def pixels(raw: Path, ip, re_) -> dict:
    out = {}
    for meta_path in sorted((raw / "stills").glob("*.json")):
        meta = re_.load_still_meta(meta_path)
        png = raw / "stills" / f"{meta_path.stem}.png"
        if re_.sha256_file(png) != meta["png_sha256"]:
            raise ValueError(f"{png}: sha256 differs from its sidecar")
        img = ip.read_png(png)
        why = re_.region_ok(meta, img.width, img.height)
        if why:
            raise ValueError(f"{png}: {why}")
        region, exclude = tuple(meta["region"]), [tuple(r) for r in meta["exclude"]]
        ground = ip.detect_organs(img, region, exclude)[1]
        out[meta_path.stem] = {**ip.field_metrics(img, region, exclude), "state": meta["state"], "ground": ground}
    return out


def measure(root: Path) -> dict:
    ip, re_ = load("instruments_py"), load("raw_evidence")
    raw = root / "raw"
    cpu = {}
    for name, rel in CPU_FILES.items():
        s = re_.cpu_summary(re_.load_cpu_csv(raw / rel))
        cpu[name] = {"mean_pct": s["mean_pct"], "window_s": s["window_s"], "max_gap_s": s["max_gap_s"], "pids": s["pids"]}
    f = re_.field_summary(re_.load_field_csv(raw / "cpu" / "working.field.csv"))
    field = {"updates_per_s": f["updates_per_s"], "hz": f["hz"], "span_s": f["span_s"]}
    return {"pixels": pixels(raw, ip, re_), "cpu": cpu, "field": field}


if __name__ == "__main__":
    json.dump(measure(Path(sys.argv[1])), sys.stdout)
