"""ACCEPTANCE CONTRACT PART — loaders + validators for the RAW evidence of the real-Desktop run (locked).

The schema is written down in contract/RAW-EVIDENCE.md. Every loader REJECTS malformed input with a ValueError that
names the file and the field: the evidence is verified by recomputation, so a sloppy file must fail, never degrade.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

DUMP_SCHEMA = "cf2-dom-dump/1"
STILL_SCHEMA = "cf2-still/1"
STATES = ("resting", "working", "needs_you", "error", "finished_unseen")
VERDICT_KEYS = ("readable_at_a_glance", "five_states_distinguishable", "not_distracting_at_rest")
SHA_RE = re.compile(r"[0-9a-f]{64}")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_json(p: Path) -> dict:
    try:
        v = json.loads(Path(p).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{p}: unreadable JSON ({e})") from e
    if not isinstance(v, dict):
        raise ValueError(f"{p}: expected a JSON object")
    return v


def _need(obj: dict, key: str, kind: type | tuple, where: str):
    if key not in obj or isinstance(obj[key], bool) and kind is not bool or not isinstance(obj[key], kind):
        raise ValueError(f"{where}: field {key!r} missing or not {kind}")
    return obj[key]


# ---- DOM dumps -------------------------------------------------------------------------------------------------------

def _row(row: dict, where: str) -> dict:
    return {"data-cf-session": row.get("data-cf-session"), "data-cf-state": row.get("data-cf-state"),
            "swatch_circles": _need(row, "swatch_circles", int, where)}


def load_dump(p: Path) -> dict:
    d = load_json(p)
    where = str(p)
    if d.get("schema") != DUMP_SCHEMA:
        raise ValueError(f"{where}: schema must be {DUMP_SCHEMA!r}")
    _need(d, "stored_id", str, where)
    if _need(d, "state", str, where) not in STATES:
        raise ValueError(f"{where}: unknown state {d['state']!r}")
    _need(d, "focused", bool, where)
    if not SHA_RE.fullmatch(_need(d, "plugin_js_sha256", str, where)):
        raise ValueError(f"{where}: plugin_js_sha256 is not a sha256")
    _need(d, "captured_at", (int, float), where)
    _need(d, "html", dict, where)
    _need(d, "strip", dict, where)
    _need(d["strip"], "text", str, where + ".strip")
    comp = _need(d, "composer", dict, where)
    _need(comp, "border_color", str, where + ".composer")
    _need(comp, "ring_vars", dict, where + ".composer")
    _need(d, "transcript_messages", int, where)
    d["row"] = _row(_need(d, "row", dict, where), where + ".row")
    rows = _need(d, "rows", list, where)
    d["rows"] = [_row(r, f"{where}.rows[{i}]") for i, r in enumerate(rows) if isinstance(r, dict)]
    if len(d["rows"]) != len(rows):
        raise ValueError(f"{where}: every entry of rows must be an object")
    return d


_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)")


def parse_css_rgb(value: str) -> tuple[int, int, int, float]:
    m = _RGB.fullmatch(value.strip())
    if not m:
        raise ValueError(f"not a computed rgb()/rgba() colour: {value!r}")
    r, g, b = (int(m.group(i)) for i in (1, 2, 3))
    if max(r, g, b) > 255:
        raise ValueError(f"channel out of range: {value!r}")
    return r, g, b, float(m.group(4) if m.group(4) is not None else 1)


# ---- stills sidecars -------------------------------------------------------------------------------------------------

def _rect(v, where: str, name: str) -> None:
    if not (isinstance(v, list) and len(v) == 4 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)):
        raise ValueError(f"{where}: {name} must be [x, y, w, h] integers")


def load_still_meta(p: Path) -> dict:
    d = load_json(p)
    where = str(p)
    if d.get("schema") != STILL_SCHEMA:
        raise ValueError(f"{where}: schema must be {STILL_SCHEMA!r}")
    if _need(d, "state", str, where) not in STATES + ("resting-idle",):
        raise ValueError(f"{where}: unknown state {d['state']!r}")
    if not SHA_RE.fullmatch(_need(d, "png_sha256", str, where)):
        raise ValueError(f"{where}: png_sha256 is not a sha256")
    _need(d, "taken_at", (int, float), where)
    _rect(_need(d, "region", list, where), where, "region")
    for r in _need(d, "exclude", list, where):
        _rect(r, where, "every exclude entry")
    return d


def region_ok(meta: dict, width: int, height: int) -> str | None:
    """None when the region/exclusions satisfy the schema's anti-cherry-picking rules, else the reason."""
    x, y, w, h = meta["region"]
    if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
        return f"region {meta['region']} is outside the {width}×{height} still"
    if w * h < 0.5 * width * height:
        return f"region covers {w * h / (width * height):.0%} of the still (< 50%): a cropped-to-taste measurement"
    excluded = sum(rw * rh for _rx, _ry, rw, rh in meta["exclude"])
    if excluded > 0.25 * w * h:
        return f"exclusions cover {excluded / (w * h):.0%} of the region (> 25%)"
    return None


# ---- CPU / field sampler CSVs ----------------------------------------------------------------------------------------

def _csv_rows(p: Path, header: list[str]) -> list[dict]:
    with open(p, newline="") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != header:
            raise ValueError(f"{p}: header must be exactly {','.join(header)}, got {rd.fieldnames}")
        return list(rd)


def load_cpu_csv(p: Path) -> list[tuple[int, float, float]]:
    out = []
    for i, r in enumerate(_csv_rows(p, ["pid", "ts", "cpu_pct"]), start=2):
        try:
            pid, ts, pct = int(r["pid"]), float(r["ts"]), float(r["cpu_pct"])
        except (TypeError, ValueError) as e:
            raise ValueError(f"{p}:{i}: unparsable row {r}") from e
        if pid <= 0 or pct < 0 or pct != pct or ts != ts:
            raise ValueError(f"{p}:{i}: pid {pid}, cpu_pct {pct}, ts {ts} are not plausible")
        out.append((pid, ts, pct))
    if not out:
        raise ValueError(f"{p}: no samples")
    if any(b[1] < a[1] for a, b in zip(out, out[1:], strict=False)):
        raise ValueError(f"{p}: timestamps go backwards")
    return out


def cpu_summary(rows: list[tuple[int, float, float]]) -> dict:
    """Per-timestamp sum over all sampled pids, then the mean over timestamps. window_s = last ts − first ts."""
    by_ts: dict[float, float] = {}
    for _pid, ts, pct in rows:
        by_ts[ts] = by_ts.get(ts, 0.0) + pct
    stamps = sorted(by_ts)
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    return {"mean_pct": sum(by_ts.values()) / len(by_ts), "window_s": stamps[-1] - stamps[0], "samples": len(stamps),
            "max_gap_s": max(gaps) if gaps else float("inf"), "pids": len({r[0] for r in rows}),
            "first_ts": stamps[0], "last_ts": stamps[-1]}


def load_field_csv(p: Path) -> list[tuple[float, str]]:
    out = []
    for i, r in enumerate(_csv_rows(p, ["ts", "css_sha256"]), start=2):
        try:
            ts = float(r["ts"])
        except (TypeError, ValueError) as e:
            raise ValueError(f"{p}:{i}: unparsable ts {r}") from e
        if not SHA_RE.fullmatch(r["css_sha256"] or ""):
            raise ValueError(f"{p}:{i}: css_sha256 is not a sha256")
        out.append((ts, r["css_sha256"]))
    if len(out) < 2 or any(b[0] < a[0] for a, b in zip(out, out[1:], strict=False)):
        raise ValueError(f"{p}: needs ≥ 2 samples in time order")
    return out


def field_summary(rows: list[tuple[float, str]]) -> dict:
    span = rows[-1][0] - rows[0][0]
    changes = sum(1 for a, b in zip(rows, rows[1:], strict=False) if a[1] != b[1])
    return {"span_s": span, "hz": (len(rows) - 1) / span if span > 0 else 0.0,
            "updates_per_s": changes / span if span > 0 else 0.0, "first_ts": rows[0][0], "last_ts": rows[-1][0]}


# ---- the vision model's raw response ---------------------------------------------------------------------------------

_VERDICT = re.compile(r"^\s*(readable_at_a_glance|five_states_distinguishable|not_distracting_at_rest)\s*:\s*(yes|no)\s*$", re.I | re.M)
_MODEL = re.compile(r"^\s*model\s*:\s*(\S.*?)\s*$", re.I | re.M)


def parse_vision(text: str) -> dict:
    found: dict[str, list[bool]] = {}
    for k, v in _VERDICT.findall(text):
        found.setdefault(k.lower(), []).append(v.lower() == "yes")
    missing = [k for k in VERDICT_KEYS if k not in found]
    if missing:
        raise ValueError(f"vision response lacks verdict line(s): {', '.join(missing)}")
    dup = [k for k, v in found.items() if len(v) != 1]
    if dup:
        raise ValueError(f"vision response states {', '.join(dup)} more than once")
    model = _MODEL.search(text)
    if not model:
        raise ValueError("vision response lacks a 'model: <name>' line")
    return {"model": model.group(1), "verdicts": {k: found[k][0] for k in VERDICT_KEYS},
            "quoted_sha256": sorted(set(SHA_RE.findall(text)))}
