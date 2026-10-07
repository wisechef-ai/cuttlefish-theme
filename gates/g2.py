#!/usr/bin/env python3
"""G2: deterministic design gate (tools/p1/CONTRACT.md section 5; thresholds frozen in gatelib.FROZEN).

    gates/.venv/bin/python gates/g2.py <manifest.json> [--direction-dir DIR] [--no-cvd]

Exit 0 = PASS, 1 = FAIL (named defects in g2.json / g2.md next to the manifest), 2 = instrument error.
Reads only the render PNGs and the direction module; nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dirtools as dt  # noqa: E402
import gatelib as gl  # noqa: E402

CONTRAST_MIN = gl.FROZEN["contrast_min"]
DELTA_MIN = gl.FROZEN["identity_delta_e_min"]


def check_authored(direction_dir: Path, man: gl.Manifest) -> tuple[dict, dict]:
    info = dt.run_node(direction_dir, [], authored=True)
    pairs = info.get("authored_pairs") or []
    rows = []
    for p in pairs:
        r = gl.contrast_ratio(p["fg"], p["bg"])
        rows.append({"fg": p["fg"], "bg": p["bg"], "where": p.get("where", ""), "ratio": round(r, 3), "ok": r >= CONTRAST_MIN})
    bad = [r for r in rows if not r["ok"]]
    return {"threshold": CONTRAST_MIN, "pairs": rows, "n": len(rows), "ok": not bad,
            "note": "direction exports no authoredPairs()" if not rows else ""}, info


def check_rendered_text(man: gl.Manifest, direction_dir: Path) -> dict:
    targets = [e for e in man.entries if e.host == "tui-terminator" and e.rung == "half" and e.scale in ("M", "S")
               and e.depth in ("truecolor", "256") and not e.tiles and len(e.sessions) <= 1]
    reqs = [dt.text_requests(e) for e in targets]
    res = dt.run_node(direction_dir, reqs)["results"] if reqs else []
    rows, imgs = [], {}
    for e, r in zip(targets, res):
        if e.file not in imgs:
            imgs[e.file] = dt.load_png(man.root / e.file)
        x0, y0 = e.crop[0], e.crop[1]
        for (bx, by, bw, bh, s) in dt.text_cell_boxes(r["text"]):
            cell = imgs[e.file][y0 + by:y0 + by + bh, x0 + bx:x0 + bx + bw]
            if cell.size == 0:
                rows.append({"file": e.file, "text": s, "ratio": 0.0, "ok": False, "error": "text box outside the render"})
                continue
            ratio = gl.measure_cell_contrast(cell)
            rows.append({"file": e.file, "look": e.look, "scale": e.scale, "depth": e.depth, "cols": e.cols, "text": s,
                         "ratio": round(ratio, 3), "ok": ratio >= CONTRAST_MIN})
    bad = [r for r in rows if not r["ok"]]
    worst = min(rows, key=lambda r: r["ratio"]) if rows else None
    return {"threshold": CONTRAST_MIN, "n": len(rows), "entries_measured": len(targets), "worst": worst,
            "failing": bad, "rows": rows, "ok": bool(rows) and not bad,
            "note": "" if rows else "no text cells could be measured on the half-truecolor/256 rungs"}


def check_identity(man: gl.Manifest, direction_dir: Path) -> dict:
    out = {"threshold": DELTA_MIN, "arc_deg": list(gl.FROZEN["identity_arc_deg"]), "grids": {}}
    for n in (16, 20):
        grids = [e for e in man.entries if e.grid_n == n and e.host == "tui-terminator"]
        if not grids:
            out["grids"][str(n)] = {"ok": False, "error": f"no {n}-session identity grid in the manifest"}
            continue
        g = min(grids, key=lambda e: e.frame_t)
        img = dt.load_png(man.root / g.file)
        tiles = sorted(g.tiles, key=lambda t: t["session_idx"])
        reqs = []
        for t in tiles:
            tw, th = t["crop"][2], t["crop"][3]
            reqs.append({"scale": "S", "w": round(tw / gl.CELL_W), "h": round(th / gl.CELL_H) * 2, "state": g.state,
                         "session_idx": t["session_idx"], "degraded": False, "t": g.frame_t, "depth": g.depth})
        texts = dt.run_node(direction_dir, reqs)["results"]
        labs, pig = [], []
        for t, r in zip(tiles, texts):
            x, y, w, h = t["crop"]
            tile = img[y:y + h, x:x + w]
            mask = np.zeros(tile.shape[:2], dtype=bool)
            for (bx, by, bw, bh, _s) in dt.text_cell_boxes(r["text"]):
                mask[by:by + bh, bx:bx + bw] = True
            labs.append(gl.median_oklab(tile, mask))
            nb = gl.non_background_mask(tile, mask)
            pig.append(gl.median_oklab(tile, ~nb) if nb.any() else labs[-1])
        chk = gl.identity_check(np.array(labs), DELTA_MIN)
        names = [t["session_idx"] for t in tiles]
        ok = chk["ok_delta"] and not chk["alarm_arc_violations"]
        worst_pair = [names[i] for i in chk["worst_indices"]] if chk["worst_indices"] else None
        pw = gl.nearest_pair(np.array(pig))
        out["grids"][str(n)] = {"file": g.file,
                                "informational_pigment_only": {"note": "NOT gating: median OKLab of non-background pixels per tile; shows identity carried by sparse pigment that the frozen tile-median cannot see",
                                                               "worst_delta_e": pw[0], "worst_pair_sessions": [names[i] for i in pw[1]] if pw[1] else None}, "sessions": names, "worst_delta_e": chk["worst_pair"], "worst_pair_sessions": worst_pair,
                                "ok_delta": chk["ok_delta"], "alarm_arc_violations": [names[i] for i in chk["alarm_arc_violations"]],
                                "tile_oklch": [[round(v, 4) for v in row] for row in chk["lch"]],
                                "matrix": [[round(v, 4) for v in row] for row in chk["matrix"]], "ok": ok}
    out["ok"] = all(g.get("ok") for g in out["grids"].values())
    return out


def check_static(man: gl.Manifest) -> dict:
    rows, bad_static, bad_working, unproven = [], [], [], []
    for key, frames in man.frame_groups().items():
        label = "|".join(str(k) for k in key)
        look = key[-1]
        if key[0] == "desktop" and len(key[5]) > 1:
            continue  # the desktop sidebar mixes sessions in all six states, so one look label cannot be judged
        if len(frames) < 2:
            if look != "working":
                unproven.append(label)
            else:
                bad_working.append(label + " (single frame)")
            continue
        imgs = [dt.load_entry_crop(man, e) for e in frames]
        same = gl.frames_identical(imgs)
        rows.append({"group": label, "look": look, "frames": [e.frame_t for e in frames], "identical": same})
        if look == "working" and same:
            bad_working.append(label)
        if look != "working" and not same:
            bad_static.append(label)
    proven = [r for r in rows if r["look"] != "working"]
    return {"groups_compared": len(rows), "nonworking_groups_proven": len(proven), "nonworking_changing": bad_static,
            "working_not_changing": bad_working, "single_frame_nonworking_unproven": unproven,
            "ok": not bad_static and not bad_working and bool(proven)}


def run(manifest_path, direction_dir_hint=None, cvd=True) -> dict:
    man = gl.load_manifest(manifest_path)
    ddir = dt.resolve_direction_dir(man.direction, direction_dir_hint)
    authored, info = check_authored(ddir, man)
    rendered = check_rendered_text(man, ddir)
    identity = check_identity(man, ddir)
    static = check_static(man)
    cvd_files = dt.ensure_cvd_images(man) if cvd else []
    defects = []
    if not authored["ok"]:
        defects.append({"code": "CONTRAST_AUTHORED", "detail": [f'{r["where"] or r["fg"]+"/"+r["bg"]}: {r["ratio"]}:1' for r in authored["pairs"] if not r["ok"]]})
    if not rendered["ok"]:
        defects.append({"code": "CONTRAST_RENDERED", "detail": [f'{r["file"]} "{r["text"]}": {r["ratio"]}:1' for r in rendered["failing"][:12]] or [rendered["note"]]})
    for n, g in identity["grids"].items():
        if g.get("error"):
            defects.append({"code": f"IDENTITY_GRID_MISSING_{n}", "detail": [g["error"]]})
            continue
        if not g["ok_delta"]:
            defects.append({"code": f"IDENTITY_DELTA_E_{n}", "detail": [f'worst pair {g["worst_pair_sessions"]} dE_OK={g["worst_delta_e"]:.4f} < {DELTA_MIN}']})
        if g["alarm_arc_violations"]:
            defects.append({"code": f"IDENTITY_ALARM_ARC_{n}", "detail": [f'sessions {g["alarm_arc_violations"]} have an identity hue outside [110,340) with chroma >= 0.03']})
    if static["nonworking_changing"]:
        defects.append({"code": "STATIC_NONWORKING_CHANGES", "detail": static["nonworking_changing"]})
    if static["working_not_changing"]:
        defects.append({"code": "WORKING_NOT_ANIMATED", "detail": static["working_not_changing"]})
    if not static["ok"] and not static["nonworking_changing"] and not static["working_not_changing"]:
        defects.append({"code": "STATIC_UNPROVEN", "detail": ["no non-working look has two frames to compare"]})
    return {"schema": "cf2909.p1.g2/1", "direction": man.direction, "manifest": str(man.path), "direction_dir": str(ddir),
            "pass": not defects, "defects": defects, "contrast_authored": authored, "contrast_rendered": rendered,
            "identity": identity, "static_proof": static, "cvd_images": len(cvd_files),
            "thresholds": {"contrast_min": CONTRAST_MIN, "identity_delta_e_min": DELTA_MIN, "identity_arc_deg": list(gl.FROZEN["identity_arc_deg"])}}


def to_markdown(r: dict) -> str:
    L = [f'# G2: {r["direction"]}: {"PASS" if r["pass"] else "FAIL"}', "",
         f'Manifest `{r["manifest"]}`; direction module `{r["direction_dir"]}`.', "", "## Defects" if r["defects"] else "## Defects: none"]
    for d in r["defects"]:
        L.append(f'- **{d["code"]}**')
        L += [f"  - {x}" for x in d["detail"]]
    ca = r["contrast_authored"]
    L += ["", f'## Contrast: authoredPairs (>= {ca["threshold"]}:1)', "", "| where | fg | bg | ratio | ok |", "|---|---|---|---|---|"]
    L += [f'| {p["where"]} | {p["fg"]} | {p["bg"]} | {p["ratio"]} | {"yes" if p["ok"] else "**NO**"} |' for p in ca["pairs"]]
    if ca["note"]:
        L.append(f'\n{ca["note"]}')
    cr = r["contrast_rendered"]
    L += ["", f'## Contrast: rendered text cells (>= {cr["threshold"]}:1, half-truecolor + 256)', "",
          f'{cr["n"]} strings over {cr["entries_measured"]} renders; worst: ' + (f'`{cr["worst"]["file"]}` "{cr["worst"]["text"]}" = {cr["worst"]["ratio"]}:1' if cr["worst"] else "n/a")]
    L += ["", "| render | text | ratio | ok |", "|---|---|---|---|"]
    L += [f'| {x["file"]} | {x["text"]} | {x["ratio"]} | {"yes" if x["ok"] else "**NO**"} |' for x in cr["rows"]]
    L += ["", f'## Identity on rendered pixels (nearest-pair dE_OK >= {r["identity"]["threshold"]}, hue arc {r["identity"]["arc_deg"]})']
    for n, g in r["identity"]["grids"].items():
        if g.get("error"):
            L.append(f'- grid {n}: **{g["error"]}**')
            continue
        L.append(f'- grid {n} (`{g["file"]}`): worst pair sessions {g["worst_pair_sessions"]} dE_OK = **{g["worst_delta_e"]:.4f}**; arc violations: {g["alarm_arc_violations"] or "none"}')
        ip = g["informational_pigment_only"]
        L.append(f'  - informational (not gating), pigment-only worst pair {ip["worst_pair_sessions"]} dE_OK = {ip["worst_delta_e"]:.4f}')
        L += ["", "  tile OKLCh (session, L, C, h):", ""]
        L += [f'  - {s}: L={v[0]:.3f} C={v[1]:.3f} h={v[2]:.1f}' for s, v in zip(g["sessions"], g["tile_oklch"])]
        L += ["", f"  dE_OK matrix {n}x{n} is in g2.json (`identity.grids.{n}.matrix`).", ""]
    s = r["static_proof"]
    L += ["", "## Static-frame proof (D1)", f'- groups compared: {s["groups_compared"]}; non-working proven identical: {s["nonworking_groups_proven"]}',
          f'- non-working that change: {s["nonworking_changing"] or "none"}', f'- working that does not change: {s["working_not_changing"] or "none"}',
          f'- single-frame non-working (unproven, warning): {len(s["single_frame_nonworking_unproven"])}',
          "", f'## CVD', f'{r["cvd_images"]} Machado-2009 images (severity 1.0, deutan/protan/tritan) written under `cvd/<kind>/` next to the manifest, for G5.', ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("--direction-dir")
    ap.add_argument("--no-cvd", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = run(a.manifest, a.direction_dir, cvd=not a.no_cvd)
    except (gl.ManifestError, dt.DirectionError, FileNotFoundError) as e:
        print(f"G2 instrument error: {e}", file=sys.stderr)
        return 2
    root = Path(a.manifest).resolve().parent
    (root / "g2.json").write_text(json.dumps(r, indent=2))
    (root / "g2.md").write_text(to_markdown(r))
    print(f'G2 {"PASS" if r["pass"] else "FAIL"} {r["direction"]}: ' + (", ".join(d["code"] for d in r["defects"]) or "no defects"))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
