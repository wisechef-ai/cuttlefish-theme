#!/usr/bin/env python3
"""Measure field_pixels.mjs output with the LOCKED instruments over the real sidecar regions/exclusions (dev-only).
    python3 tools/design/field_pixels.py <outdir>"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tests" / "acceptance"))
import instruments_py as ip  # noqa: E402

out = Path(sys.argv[1])
cases = {c["state"]: c for c in json.load(open(HERE / "field_cases.json"))}
index = json.load(open(out / "index.json"))
by = {}
for e in index:
    c = cases[e["state"]]
    img = ip.read_png(out / e["file"])
    m = ip.field_metrics(img, tuple(c["region"]), [tuple(r) for r in c["exclude"]])
    by.setdefault(e["variant"], {})[e["state"]] = {**{k: round(v, 3) for k, v in m.items()}, "drawn": e["organs"]}
for v, st in by.items():
    print(v)
    for s, m in st.items():
        print(f"  {s:16s} organs {m['organs_detected']:3d} (drawn {m['drawn']:3d})  mean_dL {m['mean_dL']:.4f}  "
              f"p95 {m['p95_dL']:.3f}  lowK {m['lowK']:.3f}  highK {m['highK']:.3f}")
    n, r = st.get("needs_you"), st.get("resting")
    if n and r:
        ratio = n['mean_dL'] / max(r['mean_dL'], 1e-9)
        print(f"  O7_5: needs_you highK {n['highK']:.3f} (>=0.6) {'OK' if n['highK'] >= 0.6 else 'FAIL'};  "
              f"mean_dL ratio {ratio:.2f} (>=2) {'OK' if n['mean_dL'] >= 2 * r['mean_dL'] else 'FAIL'}")
json.dump(by, open(out / "metrics.json", "w"), indent=1)
