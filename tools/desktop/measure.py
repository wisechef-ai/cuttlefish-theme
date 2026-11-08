#!/usr/bin/env python3
"""Recompute every number of the evidence manifest from the RAW files, with the contract's own instruments (dev only).

    python3 tools/desktop/measure.py <evidence-dir>      # <evidence-dir>/raw/... → JSON on stdout
    python3 tools/desktop/measure.py centroid <png> '{"region":[..],"exclude":[..]}'   # the field ink centre of one still

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
# The contract's share rule (tests/acceptance/raw_evidence.py region_ok) and the harness' small-window floor.
# Both mirror desktop-side evidence_lib.ts (MAX_EXCLUDED_SHARE, MIN_MEASURED_PX); test_measure.py pins them.
MAX_EXCLUDED_SHARE = 0.25
MIN_MEASURED_PX = 200_000


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"_cf_{name}", ACCEPT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def exclusion_verdict(area: int, excluded: int, min_measured: int = MIN_MEASURED_PX) -> dict:
    """The honest small-window rule (mirror of evidence_lib.ts exclusionVerdict). A share above 25 % is allowed while at least
    `min_measured` px remain measurable; fewer fails whatever the share. Both numbers are always reported."""
    if area <= 0:
        raise ValueError(f"region area must be positive, got {area}")
    measured, share = area - excluded, excluded / area
    base = {"area": area, "excluded": excluded, "share": share, "measured": measured}
    if measured < min_measured:
        return {**base, "ok": False, "reason": f"{measured} px measured < {min_measured} px: too little field left to measure"}
    if share <= MAX_EXCLUDED_SHARE:
        return {**base, "ok": True, "reason": None}
    why = f"small window: {round(share * 100)}% excluded (> 25%), {measured} px measured (>= {min_measured})"
    return {**base, "ok": True, "reason": why}


def union_area(rects, region) -> int:
    """Pixels of `region` covered by the union of `rects` (overlaps counted once)."""
    rx, ry, rw, rh = region
    seen = set()
    for x, y, w, h in rects:
        for j in range(max(y, ry), min(y + h, ry + rh)):
            for i in range(max(x, rx), min(x + w, rx + rw)):
                seen.add((i, j))
    return len(seen)


def check_still(re_, meta: dict, width: int, height: int) -> dict:
    """Raises ValueError unless the still's region and exclusions are measurable; returns the verdict with both numbers.
    The contract's bounds and 50 % region rule run first (region_ok, with no exclusions); the share rule is the honest one above."""
    why = re_.region_ok({**meta, "exclude": []}, width, height)
    if why:
        raise ValueError(why)
    region, exclude = tuple(meta["region"]), [tuple(r) for r in meta["exclude"]]
    v = exclusion_verdict(region[2] * region[3], union_area(exclude, region))
    if not v["ok"]:
        raise ValueError(v["reason"])
    return v


def centroid_of(png: Path, region, exclude) -> dict | None:
    """The centre of the field ink of a still (the instrument's own ink mask), absolute pixel coordinates; None when there is no ink."""
    ip = load("instruments_py")
    img = ip.read_png(png)
    _ground, ink = ip._ink_mask(img, tuple(region), [tuple(r) for r in exclude])
    if not ink:
        return None
    n = len(ink)
    return {"cx": sum(x for x, _ in ink) / n, "cy": sum(y for _, y in ink) / n, "n": n}


def pixels(raw: Path, ip, re_) -> dict:
    out = {}
    for meta_path in sorted((raw / "stills").glob("*.json")):
        meta = re_.load_still_meta(meta_path)
        png = raw / "stills" / f"{meta_path.stem}.png"
        if re_.sha256_file(png) != meta["png_sha256"]:
            raise ValueError(f"{png}: sha256 differs from its sidecar")
        img = ip.read_png(png)
        try:
            v = check_still(re_, meta, img.width, img.height)
        except ValueError as e:
            raise ValueError(f"{png}: {e}") from e
        region, exclude = tuple(meta["region"]), [tuple(r) for r in meta["exclude"]]
        ground = ip.detect_organs(img, region, exclude)[1]
        out[meta_path.stem] = {**ip.field_metrics(img, region, exclude), "state": meta["state"], "ground": ground,
                               "exclusion": {"area": v["area"], "excluded_px": v["excluded"], "measured_px": v["measured"],
                                             "share": round(v["share"], 6), "reason": v["reason"]}}
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
    if sys.argv[1:2] == ["centroid"]:  # measure.py centroid <png> '{"region": [...], "exclude": [...]}'  → the frame's ink centre
        spec = json.loads(sys.argv[3])
        json.dump(centroid_of(Path(sys.argv[2]), spec["region"], spec["exclude"]), sys.stdout)
    else:
        json.dump(measure(Path(sys.argv[1])), sys.stdout)
