"""ACCEPTANCE CONTRACT PART 2 — more validators for the RAW evidence (locked with the parts).

`raw_evidence.py` is locked; this sits beside it. Closes luna-parts L5 (CPU windows bound to a real toggle),
L6 (exclusion rects, empty transcript), M1 (paths stay under raw/), M2 (still labels).
Schema additions are written in contract/PARTS-2.md.
"""
from __future__ import annotations

from pathlib import Path

from .raw_evidence import load_json

RAW_ROOT = "evidence/v2/raw"
WINDOW_SCHEMA = "cf2-window-dump/1"
CPU_WINDOWS = ("idle_on", "idle_off", "working_on", "working_off")
ROLES = ("renderer", "gpu")


# ---- M1: containment -------------------------------------------------------------------------------------------------

def contained(raw_root: Path, rel: str) -> Path:
    """`rel` (relative to the raw root, or repo-relative starting with evidence/v2/raw/) resolved, and proven to live under the raw root."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")) or Path(rel).is_absolute():
        raise ValueError(f"{rel!r}: an absolute or empty path escapes {RAW_ROOT}/")
    if rel.startswith("evidence/") and not rel.startswith(RAW_ROOT + "/"):
        raise ValueError(f"{rel!r} points into evidence/ but not under {RAW_ROOT}/")
    text = rel.removeprefix(RAW_ROOT + "/")
    if ".." in Path(text).parts or "\x00" in text:
        raise ValueError(f"{rel!r}: '..' escapes {RAW_ROOT}/")
    resolved = (raw_root / text).resolve()
    if raw_root.resolve() not in resolved.parents:
        raise ValueError(f"{rel!r} resolves to {resolved}, outside {raw_root}")
    return resolved


def manifest_paths(m: dict) -> list[tuple[str, str]]:
    """Every path-valued field of the manifest that must point into the raw tree: (where, path)."""
    out = [(f"raw.files[{i}]", f["path"]) for i, f in enumerate(m["raw"]["files"])]
    out += [(f"raw.cpu.{k}", v) for k, v in m["raw"]["cpu"].items()]
    out.append(("raw.idle_window", m["raw"]["idle_window"]["dom_dump"]))
    out += [(f"capture.sessions[{i}]", s["dom_dump"]) for i, s in enumerate(m["capture"]["sessions"])]
    for i, s in enumerate(m["capture"]["stills"]):
        out.append((f"capture.stills[{i}].path", s["path"]))
        out += [(f"capture.stills[{i}].{k}", s[k]) for k in ("meta", "dom_dump") if k in s]
    out.append(("vision.file", m["vision"]["file"]))
    out += [(f"raw.cpu_windows.{k}.{f}", v[f]) for k, v in m["raw"].get("cpu_windows", {}).items() for f in ("file", "dom_dump") if f in v]
    return out


def path_problems(raw_root: Path, m: dict) -> list[str]:
    bad = []
    for where, rel in manifest_paths(m):
        try:
            contained(raw_root, rel)
        except ValueError as e:
            bad.append(f"{where}: {e}")
    return bad


# ---- M2: still labels --------------------------------------------------------------------------------------------------

def label_problems(entries: list[dict], metas: list[dict]) -> list[str]:
    """entries: manifest capture.stills that have a sidecar (parallel to `metas`)."""
    bad = []
    for i, (e, meta) in enumerate(zip(entries, metas, strict=True)):
        if e.get("state") != meta["state"]:
            bad.append(f"stills[{i}]: the manifest says {e.get('state')!r}, the sidecar says {meta['state']!r}")
    states = [meta["state"] for meta in metas]
    bad += [f"state {s!r} is measured {states.count(s)} times" for s in sorted({s for s in states if states.count(s) > 1})]
    return bad


# ---- L6: exclusion rectangles ------------------------------------------------------------------------------------------

def rect_problems(meta: dict, width: int, height: int) -> list[str]:
    bad = []
    for i, (x, y, w, h) in enumerate(meta["exclude"]):
        if w <= 0 or h <= 0:
            bad.append(f"exclude[{i}] {[x, y, w, h]} has a non-positive size (it could cancel other exclusions)")
        elif x < 0 or y < 0 or x + w > width or y + h > height:
            bad.append(f"exclude[{i}] {[x, y, w, h]} is outside the {width}×{height} still")
    return bad


# ---- L5: CPU windows bound to a real toggle ---------------------------------------------------------------------------

def load_window_dump(p: Path) -> dict:
    d = load_json(p)
    if d.get("schema") != WINDOW_SCHEMA:
        raise ValueError(f"{p}: schema must be {WINDOW_SCHEMA!r}")
    if d.get("plugin") not in ("on", "off"):
        raise ValueError(f"{p}: plugin must be 'on' or 'off'")
    if not isinstance(d.get("captured_at"), (int, float)) or isinstance(d.get("captured_at"), bool):
        raise ValueError(f"{p}: captured_at must be a number")
    if not isinstance(d.get("html"), dict) or not isinstance(d.get("rows"), list):
        raise ValueError(f"{p}: html must be an object and rows a list")
    return d


def toggle_problems(name: str, dump: dict, first_ts: float, last_ts: float) -> list[str]:
    """A window's dump must be taken inside it and show the plugin exactly as its on/off label says."""
    want_on = name.endswith("_on")
    bad = []
    if not first_ts <= dump["captured_at"] <= last_ts:
        bad.append(f"{name}: the dump was taken at {dump['captured_at']}, outside the window [{first_ts}, {last_ts}]")
    if dump["plugin"] != ("on" if want_on else "off"):
        bad.append(f"{name}: the dump says plugin {dump['plugin']!r}")
    state = dump["html"].get("data-cf-state")
    swatches = sum(1 for r in dump["rows"] if isinstance(r, dict) and r.get("swatch_circles", 0) > 0)
    cf_attrs = [k for k in dump["html"] if k.startswith("data-cf")]
    if want_on and not (state and swatches >= 1):
        bad.append(f"{name}: an 'on' window must show html[data-cf-state] and at least one swatch (state={state!r}, swatches={swatches})")
    if not want_on and (cf_attrs or swatches):
        bad.append(f"{name}: an 'off' window shows the plugin ({cf_attrs}, {swatches} swatches)")
    return bad


def role_problems(roles: dict[str, dict[str, str]]) -> list[str]:
    """roles: window name → {pid: role}. Every window samples the same multiset of roles, containing renderer and gpu."""
    bad = []
    sig = {n: sorted(r.values()) for n, r in roles.items()}
    for n, s in sig.items():
        if any(role not in s for role in ROLES) or any(v not in ROLES + ("main",) for v in s):
            bad.append(f"{n}: roles {s} must include renderer and gpu (and may add main)")
    if len({tuple(s) for s in sig.values()}) > 1:
        bad.append(f"the windows sample different pid roles: {sig}")
    return bad


def order_problems(spans: dict[str, tuple[float, float]], order: list[str]) -> list[str]:
    bad = []
    if sorted(order) != sorted(spans):
        return [f"cpu_order {order} must list exactly {sorted(spans)}"]
    ranked = sorted(spans, key=lambda n: spans[n][0])
    if ranked != order:
        bad.append(f"cpu_order says {order}, the timestamps say {ranked}")
    for a, b in zip(ranked, ranked[1:], strict=False):
        if spans[b][0] <= spans[a][1]:
            bad.append(f"windows {a} and {b} overlap")
    return bad

