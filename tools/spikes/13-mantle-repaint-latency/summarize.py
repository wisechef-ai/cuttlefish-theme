#!/usr/bin/env python3
"""Spike 13: aggregate run.py results.json files into the G3 decision. Usage: summarize.py <results.json>... [--json out]
Invalid runs are listed with their reasons and never scored. Per config: valid-run count, each run's anim−off p95
point + 95 % bootstrap CI + per-round deltas, and the gate class via settle.classify_gate (>= 3 valid runs that
unanimously pass/fail, else indeterminate)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settle as S


def cfg_key(meta):
    return f"fps{meta['fps']}-q{meta.get('quant', '0')}-memo{meta.get('memo', '0')}-rle{meta.get('rle', '0')}"


def summarize(paths):
    by = {}
    for p in paths:
        r = json.load(open(p)); k = cfg_key(r["meta"])
        row = {"path": p, "valid": r.get("valid", False), "problems": r.get("problems", ["legacy run: no validity contract"])}
        if row["valid"]:
            v = r["verdict_inputs"]
            row.update({k2: v[k2] for k2 in ("p95_off", "p95_static", "p95_anim", "anim_minus_off_p95_ms", "anim_minus_off_p95_ci95",
                                              "static_minus_off_p95_ms", "static_minus_off_p95_ci95", "per_round_anim_minus_off_p95",
                                              "g3_run_class", "g3_static_run_class", "static_idle_bytes", "static_idle_cpu_pct",
                                              "off_idle_bytes", "off_idle_cpu_pct", "anim_bytes_per_s", "anim_cpu_pct")})
        by.setdefault(k, []).append(row)
    out = {}
    for k, rows in sorted(by.items()):
        val = [x for x in rows if x["valid"]]
        out[k] = {"runs": rows, "valid_runs": len(val), "invalid_runs": len(rows) - len(val),
                  "g3_anim": S.classify_gate([x["g3_run_class"] for x in val]),
                  "g3_static": S.classify_gate([x["g3_static_run_class"] for x in val])}
        raws = [os.path.join(os.path.dirname(x["path"]), "latency-raw.json") for x in val]
        if len(val) >= 2 and all(os.path.exists(r) for r in raws):
            L = [json.load(open(r)) for r in raws]
            ok = lambda xs: [v for v in xs if v is not None]
            for c in ("anim", "static"):
                pairs = [(ok(l["off"]), ok(l[c])) for l in L]
                pa = S.pctl(sum((q for _, q in pairs), []), .95) - S.pctl(sum((o for o, _ in pairs), []), .95)
                out[k][f"pooled_{c}_minus_off_p95"] = {"point": pa, "ci95": S.pooled_delta_ci(pairs),
                                                       "keys_per_condition": sum(len(o) for o, _ in pairs)}
    return out


def main(argv):
    js = None
    if "--json" in argv:
        i = argv.index("--json"); js = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    out = summarize(argv)
    for k, c in out.items():
        print(f"\n{k}: valid {c['valid_runs']}/{len(c['runs'])}  G3 anim={c['g3_anim']}  static={c['g3_static']}")
        for cc in ("anim", "static"):
            pp = c.get(f"pooled_{cc}_minus_off_p95")
            if pp:
                print(f"  pooled (secondary, not gating) {cc}−off p95 {pp['point']:+.2f} ms, 95% CI [{pp['ci95'][0]:+.2f},{pp['ci95'][1]:+.2f}] over {pp['keys_per_condition']} keys/condition")
        for x in c["runs"]:
            if not x["valid"]:
                print(f"  INVALID {os.path.basename(os.path.dirname(x['path']))}: {len(x['problems'])} problem(s), e.g. {x['problems'][0]}")
                continue
            lo, hi = x["anim_minus_off_p95_ci95"]; slo, shi = x["static_minus_off_p95_ci95"]
            rd = ", ".join(f"{d:+.1f}" for d in x["per_round_anim_minus_off_p95"])
            print(f"  {os.path.basename(os.path.dirname(x['path']))}: p95 off/static/anim {x['p95_off']:.1f}/{x['p95_static']:.1f}/{x['p95_anim']:.1f}"
                  f"  anim−off {x['anim_minus_off_p95_ms']:+.2f} [{lo:+.1f},{hi:+.1f}] {x['g3_run_class']}"
                  f"  static−off {x['static_minus_off_p95_ms']:+.2f} [{slo:+.1f},{shi:+.1f}]  rounds [{rd}]"
                  f"  idle off/static {x['off_idle_bytes']}/{x['static_idle_bytes']} B  cpu {x['off_idle_cpu_pct']:.1f}/{x['static_idle_cpu_pct']:.1f}%"
                  f"  anim {x['anim_bytes_per_s']:.0f} B/s {x['anim_cpu_pct']:.1f}%")
    if js:
        json.dump(out, open(js, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
