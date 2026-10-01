#!/usr/bin/env python3
"""Check a P1 render manifest against CONTRACT §4 — the gate lane and CI both run this.

    python3 tools/p1/check_manifest.py <renders>/<direction-id>/manifest.json [--hosts tui,pane,desktop]

Checks (each a named failure, exit 1 on any):
  schema        top-level keys, schema id, entry fields and their types/enums
  matrix        every required (host, scale, state/look, rung, depth, cols, frame_t) entry is present
  files         every PNG exists; every crop lies inside its PNG
  static        each non-working look has its frames byte-identical in pixels inside the crop (D1)
  working       working frames are NOT all identical (the motion is real)
  capture_log   every entry has a log naming both SHAs, a throwaway HERMES_HOME and a host process
                (node …/ui-tui/dist/entry.js for TUI, electron for desktop) whose PID matches the host's ack
Prints one JSON report on stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = "cf2909.p1.manifest/1"
STATES = ("idle", "working", "review", "needs-you", "fault", "unknown")
HOSTS = ("tui-terminator", "tui-pane-webgl", "tui-pane-dom", "desktop")
WORKING_T = (0.0, 0.25, 0.5, 0.75)
LOOKS = STATES + ("degraded",)
ENTRY_TYPES = {"file": str, "host": str, "scale": str, "state": str, "rung": str, "depth": str, "frame_t": (int, float),
               "sessions": list, "crop": list, "capture_log": str}


def look(e: dict) -> str:
    return "degraded" if e.get("degraded") else e["state"]


def required(hosts: set[str]) -> list[tuple]:
    """(host, scale, look, rung, depth, cols, view) keys of the CONTRACT §4 matrix; frames are checked separately."""
    req = []
    if "tui" in hosts:
        for depth, cols in (("truecolor", 120), ("256", 120), ("truecolor", 80)):
            req += [("tui-terminator", "M", lk, "half", depth, cols, "mantle") for lk in LOOKS]
        req += [("tui-terminator", "S", st, "half", "truecolor", 120, "pill") for st in STATES]
        req += [("tui-terminator", "S", "idle", "half", "truecolor", 120, f"grid{n}") for n in (16, 20)]
    if "pane" in hosts:
        for r in ("webgl", "dom"):
            req += [(f"tui-pane-{r}", "M", lk, "bg", "truecolor", 120, "mantle") for lk in LOOKS]
    if "desktop" in hosts:
        for scale in ("XL", "M", "S"):
            req += [("desktop", scale, lk, "dom", "truecolor", None, "surface") for lk in LOOKS]
        req.append(("desktop", "S", "idle", "dom", "truecolor", None, "sidebar20"))
    return req


def view_of(e: dict) -> str:
    n = len(e.get("sessions") or [])
    if e["host"] == "desktop":
        return "sidebar20" if n == 20 else "surface"
    if e["scale"] == "S":
        return f"grid{n}" if n in (16, 20) else "pill"
    return "mantle"


def key_of(e: dict) -> tuple:
    return (e["host"], e["scale"], look(e), e["rung"], e["depth"], e.get("cols"), view_of(e))


def crop_pixels(png: Path, crop):
    from PIL import Image
    im = Image.open(png).convert("RGB")
    x, y, w, h = crop
    return im.crop((x, y, x + w, y + h)).tobytes(), im.size


def check(manifest_path: Path, hosts: set[str], live_pids: bool = False) -> dict:
    root = manifest_path.parent
    fails: dict[str, list] = defaultdict(list)
    try:
        m = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        return {"ok": False, "fails": {"schema": [f"unreadable manifest: {exc}"]}}

    for k in ("schema", "direction", "hermes_sha", "plugin_sha", "entries"):
        if k not in m:
            fails["schema"].append(f"missing top-level {k}")
    if m.get("schema") != SCHEMA:
        fails["schema"].append(f"schema {m.get('schema')!r} != {SCHEMA}")
    for k in ("hermes_sha", "plugin_sha"):
        if not re.fullmatch(r"[0-9a-f]{7,40}", str(m.get(k, ""))):
            fails["schema"].append(f"{k} {m.get(k)!r} is not a git sha")
    entries = m.get("entries") or []
    for i, e in enumerate(entries):
        for k, t in ENTRY_TYPES.items():
            if not isinstance(e.get(k), t):
                fails["schema"].append(f"entry {i}: {k} missing or not {t}")
        if e.get("host") not in HOSTS:
            fails["schema"].append(f"entry {i}: host {e.get('host')!r}")
        if e.get("scale") not in ("XL", "M", "S"):
            fails["schema"].append(f"entry {i}: scale {e.get('scale')!r}")
        if e.get("state") not in STATES:
            fails["schema"].append(f"entry {i}: state {e.get('state')!r}")
        if e.get("rung") not in ("half", "bg", "dom") or e.get("depth") not in ("truecolor", "256"):
            fails["schema"].append(f"entry {i}: rung/depth {e.get('rung')!r}/{e.get('depth')!r}")
        if not (isinstance(e.get("crop"), list) and len(e["crop"]) == 4 and all(isinstance(v, int) for v in e["crop"])
                and e["crop"][2] > 0 and e["crop"][3] > 0):
            fails["schema"].append(f"entry {i}: crop {e.get('crop')!r} is not [x, y, w, h] ints")
    if fails["schema"]:
        return {"ok": False, "entries": len(entries), "fails": dict(fails)}

    groups: dict[tuple, list] = defaultdict(list)
    for e in entries:
        groups[key_of(e)].append(e)
    for k in required(hosts):
        frames = sorted(e["frame_t"] for e in groups.get(k, []))
        if k[2] == "working":
            if frames != list(WORKING_T):
                fails["matrix"].append(f"{k}: working frames {frames} != {list(WORKING_T)}")
        elif len(frames) < 2 or len(set(frames)) < 2:
            fails["matrix"].append(f"{k}: needs 2 frames at different t, has {frames}")

    for k, es in groups.items():
        shots = []
        for e in es:
            png = root / e["file"]
            if not png.exists():
                fails["files"].append(f"{e['file']}: missing")
                continue
            try:
                px, size = crop_pixels(png, e["crop"])
                # Grids carry per-tile crops: the static proof compares only what the host PAINTED, never the
                # host's own chrome inside the bbox (desktop sidebar rows show a wall-clock age, "10m").
                if e.get("tiles"):
                    px = b"".join(crop_pixels(png, t["crop"])[0] for t in e["tiles"])
            except OSError as exc:
                fails["files"].append(f"{e['file']}: {exc}")
                continue
            x, y, w, h = e["crop"]
            if x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
                fails["files"].append(f"{e['file']}: crop {e['crop']} outside {size}")
            shots.append((e["frame_t"], px, e["file"]))
        if len(shots) < 2:
            continue
        distinct = {px for _, px, _ in shots}
        if k[2] == "working":
            if len(distinct) < 2:
                fails["working"].append(f"{k}: all {len(shots)} working frames identical (no motion)")
        elif len(distinct) != 1:
            fails["static"].append(f"{k}: {len(distinct)} distinct frames for a static look "
                                   f"({', '.join(f for _, _, f in shots)})")

    for e in entries:
        lp = root / e["capture_log"]
        if not lp.exists():
            fails["capture_log"].append(f"{e['file']}: no log {e['capture_log']}")
            continue
        text = lp.read_text(errors="replace")
        problems = log_problems(text, e, m)
        if live_pids:
            problems += pid_problems(text)
        for p in problems:
            fails["capture_log"].append(f"{e['capture_log']}: {p}")
    return {"ok": not any(fails.values()), "direction": m.get("direction"), "entries": len(entries),
            "required": len(required(hosts)), "fails": {k: v for k, v in fails.items() if v}}


def _field(text: str, name: str) -> str | None:
    mm = re.search(rf"^{name}: (.*)$", text, re.M)
    return mm.group(1).strip() if mm else None


def log_problems(text: str, e: dict, m: dict) -> list[str]:
    out = []
    if _field(text, "hermes_sha") != m.get("hermes_sha"):
        out.append("hermes_sha differs from the manifest")
    if _field(text, "plugin_sha") != m.get("plugin_sha"):
        out.append("plugin_sha differs from the manifest")
    if not _field(text, "command"):
        out.append("no command line")
    home = _field(text, "hermes_home") or ""
    if not home or re.search(r"/\.hermes/?$", home):
        out.append(f"hermes_home {home!r} is not a throwaway dir")
    rows = host_rows(text)
    want = re.compile(r"electron" if e["host"] == "desktop" else r"node\b.*ui-tui/dist/entry\.js")
    hits = [r for r in rows if want.search(r[2])]
    if not hits:
        out.append(f"ps names no {'electron' if e['host'] == 'desktop' else 'hermes TUI (ui-tui/dist/entry.js)'} process")
    if e["host"] != "desktop":
        ack = _field(text, "ack")
        try:
            pid = json.loads(ack).get("pid") if ack else None
        except ValueError:
            pid = None
        if pid is None or pid not in {r[0] for r in hits}:
            out.append(f"the widget's ack pid {pid} is not a TUI process in the ps")
    return out


def host_rows(text: str) -> list[tuple[int, int, str]]:
    rows = []
    for line in text.split("ps (host process tree at capture):", 1)[-1].splitlines():
        mm = re.match(r"^(\d+) (\d+) (\d+) (.*)$", line)
        if mm:
            rows.append((int(mm.group(1)), int(mm.group(2)), mm.group(4)))
    return rows


def pid_problems(text: str) -> list[str]:
    """Live check, only meaningful DURING a capture run (pids die with the host)."""
    import os
    return [f"pid {p} not alive" for p, _, _ in host_rows(text)[:1] if not os.path.exists(f"/proc/{p}")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--hosts", default=None, help="tui,pane,desktop (default: the manifest's own `hosts`)")
    ap.add_argument("--live-pids", action="store_true", help="also require each log's host pid to be alive NOW "
                                                              "(only meaningful while the capture's hosts still run)")
    ns = ap.parse_args(argv)
    hosts = ns.hosts
    if hosts is None:
        try:
            hosts = ",".join(json.loads(ns.manifest.read_text()).get("hosts") or ["tui", "pane", "desktop"])
        except (OSError, ValueError):
            hosts = "tui,pane,desktop"
    rep = check(ns.manifest, {h.strip() for h in hosts.split(",") if h.strip()}, live_pids=ns.live_pids)
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
