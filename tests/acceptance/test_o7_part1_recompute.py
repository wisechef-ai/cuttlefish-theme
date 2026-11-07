"""ACCEPTANCE CONTRACT PART 1 — O7 by RECOMPUTATION from raw artifacts (closes luna F4, F5-idle-floor, F9-composer/strip) (locked).

Locked O7 trusts numbers the manifest author typed. Here the harness must also leave RAW files under evidence/v2/raw/
(schema: contract/RAW-EVIDENCE.md) and every number the manifest claims is RECOMPUTED from them:
  dom_state, rows_with_swatch/rows_total ← DOM dumps          | p95_dL, organs_detected, highK, mean_dL ← PNG stills, with the
  same maths as O2's instruments (tests/acceptance/instruments_py.py, pinned to instruments.ts) | idle/working CPU on−off ←
  the pid,ts,cpu_pct sampler CSVs | field_updates_per_s ← the css-hash sampler | vision verdicts ← the model's raw response.
Every raw file's sha256 and the plugin.js sha are bound into the manifest; the vision response must quote every still it judged.
Floors next to the ceilings (F5): a still taken INSIDE the idle-CPU window shows ≥ 20 organs, so idle CPU is measured WITH a field.
F9: the DOM dumps carry the status-strip words and the computed composer border colour of each focused state.

RESIDUAL RISK (stated, not hidden): a harness that fabricates the raw files themselves passes this part. What it cannot do
cheaply is keep the PNG pixels, the sampler timestamps, the DOM dumps and the model's quoted hashes mutually consistent;
the sol review (M5) reads the harness code that produced them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from . import instruments_py as ip
from . import raw_evidence as re_
from .helpers import ROOT

MANIFEST = ROOT / "evidence" / "v2" / "manifest.json"
RAW_ROOT = "evidence/v2/raw"
VEC = json.loads((ROOT / "contract" / "config-vectors.json").read_text())
LABELS = {k: v["label"] for k, v in VEC["defaults"]["states"].items()}
MIN_WINDOW_S = 60
MAX_GAP_S = 2.5
FLOOR_ORGANS = 20
# the field belongs to the FOCUSED session, and focusing clears finished_unseen: its pixels live in the sidebar swatch, not the field
FIELD_STATES = ("resting", "working", "needs_you", "error")
TOL = 1e-4


# ---- fixtures --------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def m() -> dict:
    assert MANIFEST.is_file(), f"{MANIFEST.relative_to(ROOT)} missing: run the real-Desktop harness (make evidence)"
    return json.loads(MANIFEST.read_text())


@pytest.fixture(scope="module")
def raw(m) -> Path:
    spec = m.get("raw")
    assert isinstance(spec, dict) and spec.get("root") == RAW_ROOT and isinstance(spec.get("files"), list), \
        f"manifest.raw must be {{root: {RAW_ROOT!r}, files: [{{path, sha256}}…]}} (contract/RAW-EVIDENCE.md)"
    root = ROOT / RAW_ROOT
    assert root.is_dir(), f"{RAW_ROOT}/ missing"
    return root


@pytest.fixture(scope="module")
def dumps(m, raw) -> dict[str, dict]:
    out = {}
    for s in m["capture"]["sessions"]:
        assert "dom_dump" in s, f"session {s.get('stored_id')}: no dom_dump path in the manifest"
        out[s["stored_id"]] = re_.load_dump(raw / s["dom_dump"])
    return out


@pytest.fixture(scope="module")
def pixels(m, raw) -> dict[str, dict]:
    """state → {metrics, meta, png} recomputed from the PNG stills."""
    out = {}
    for s in (x for x in m["capture"]["stills"] if "meta" in x):
        meta = re_.load_still_meta(raw / s["meta"])
        png = raw / s["path"].removeprefix(RAW_ROOT + "/")
        assert png.is_file(), f"{s['path']} missing"
        assert meta["png_sha256"] == re_.sha256_file(png) == s["sha256"], f"{s['path']}: sha256 disagrees (meta / file / manifest)"
        img = ip.read_png(png)
        why = re_.region_ok(meta, img.width, img.height)
        assert why is None, f"{s['path']}: {why}"
        metrics = ip.field_metrics(img, tuple(meta["region"]), [tuple(r) for r in meta["exclude"]])
        out[meta["state"]] = {"metrics": metrics, "meta": meta, "size": (img.width, img.height)}
    return out


# ---- F4: binding -----------------------------------------------------------------------------------------------------

def test_R1_every_raw_file_is_bound_by_sha256_and_nothing_unlisted_exists(m, raw):
    listed = {f["path"]: f["sha256"] for f in m["raw"]["files"]}
    assert len(listed) == len(m["raw"]["files"]), "a raw file is listed twice"
    on_disk = {p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    assert on_disk == set(listed), f"unlisted: {sorted(on_disk - set(listed))}, missing: {sorted(set(listed) - on_disk)}"
    for rel, sha in listed.items():
        assert re_.sha256_file(raw / rel) == sha, f"{rel}: sha256 differs from the manifest"
    assert {"dom", "stills", "cpu", "vision"} <= {p.split("/")[0] for p in listed}, "all four artifact kinds are present"


def test_R2_the_plugin_under_test_is_the_plugin_in_this_tree(m, dumps, raw):
    here = re_.sha256_file(ROOT / "desktop" / "plugin.js")
    assert m["plugin_js_sha256"] == here
    idle = re_.load_dump(raw / m["raw"]["idle_window"]["dom_dump"])
    for name, d in {**dumps, "idle-window": idle}.items():
        assert d["plugin_js_sha256"] == here, f"{name}: the DOM was dumped from a different plugin.js"


# ---- F4: dom_state ---------------------------------------------------------------------------------------------------

def test_R3_dom_state_is_what_the_dumps_say(m, dumps):
    sessions = m["capture"]["sessions"]
    assert len(sessions) >= 4 and len({d["state"] for d in dumps.values()}) >= 4
    for s in sessions:
        d = dumps[s["stored_id"]]
        assert d["row"]["data-cf-session"] == s["stored_id"], "the dump's row belongs to another session"
        assert d["state"] == s["expected"], f"{s['stored_id']}: the dump was taken for {d['state']}, the manifest expects {s['expected']}"
        assert d["row"]["data-cf-state"] == s["dom_state"] == s["expected"], \
            f"{s['stored_id']}: dump says {d['row']['data-cf-state']}, manifest dom_state {s['dom_state']}, scenario {s['expected']}"


def test_R4_rows_and_swatches_are_counted_from_the_dumps(m, dumps):
    row_sets = {tuple(sorted((r["data-cf-session"] or "") for r in d["rows"])) for d in dumps.values()}
    assert len(row_sets) == 1, "the dumps disagree about which sidebar rows exist"
    rows = next(iter(dumps.values()))["rows"]
    swatched = sum(1 for r in rows if r["swatch_circles"] > 0 and r["data-cf-session"])
    assert (m["capture"]["rows_total"], m["capture"]["rows_with_swatch"]) == (len(rows), swatched)
    assert swatched == len(rows) >= 4, "every sidebar row carries a drawn swatch"


# ---- F9: strip + composer from the real DOM --------------------------------------------------------------------------

def _focused(dumps: dict[str, dict]) -> dict[str, dict]:
    """The dumps taken with their session focused: html/strip/composer describe THAT session (a finished_unseen session
    cannot be focused: focusing clears it, so its dump is judged by its sidebar row alone)."""
    out = {sid: d for sid, d in dumps.items() if d["focused"]}
    assert len({d["state"] for d in out.values()}) >= 4, "at least four DIFFERENT states were captured with their session focused"
    return out


def test_R5_the_status_strip_says_the_focused_state_in_words(dumps):
    dumps = _focused(dumps)
    for sid, d in dumps.items():
        assert d["html"].get("data-cf-state") == d["state"], f"{sid}: html[data-cf-state] is {d['html'].get('data-cf-state')}"
        label = LABELS[d["state"]]
        if label:
            assert label.lower() in d["strip"]["text"].lower(), f"{sid}: the strip says {d['strip']['text']!r}, not {label!r}"
    texts = {d["state"]: d["strip"]["text"].strip().lower() for d in dumps.values()}
    assert len(set(texts.values())) == len(texts), f"the strip does not tell the states apart: {texts}"


def test_R6_the_composer_ring_is_state_dependent_in_computed_style(dumps):
    by_state = {d["state"]: d for d in _focused(dumps).values()}
    assert {"resting", "needs_you"} <= set(by_state), "the capture must include a focused resting and a focused needs_you dump"
    a, b = by_state["resting"]["composer"], by_state["needs_you"]["composer"]
    assert re_.parse_css_rgb(a["border_color"]) != re_.parse_css_rgb(b["border_color"]), \
        f"computed composer border is {a['border_color']} at rest and while needing you: the ring does not speak"
    for d in by_state.values():
        for var in ("--dt-composer-ring", "--composer-ring-strength"):
            assert str(d["composer"]["ring_vars"].get(var, "")).strip(), f"{d['state']}: {var} is not set in the real DOM"


# ---- F4: pixels ------------------------------------------------------------------------------------------------------

def test_R7_field_pixels_are_recomputed_from_the_png_stills_and_equal_the_manifest(m, pixels):
    claimed = m["field_pixels"]
    assert set(FIELD_STATES) <= set(claimed), f"field_pixels must cover {FIELD_STATES}, has {sorted(claimed)}"
    for state in FIELD_STATES:
        assert state in pixels, f"no still for {state}"
        got, want = pixels[state]["metrics"], claimed[state]
        assert got["organs_detected"] == want["organs_detected"], \
            f"{state}: {got['organs_detected']} organs in the pixels, manifest says {want['organs_detected']}"
        for k in ("p95_dL", "mean_dL", "lowK", "highK"):
            assert abs(got[k] - want[k]) <= TOL, f"{state}.{k}: recomputed {got[k]:.5f}, manifest {want[k]:.5f}"


def test_R8_the_recomputed_pixels_meet_the_language(pixels):
    rest, need = pixels["resting"]["metrics"], pixels["needs_you"]["metrics"]
    assert rest["p95_dL"] <= 0.05, f"resting p95 ΔL {rest['p95_dL']:.4f} on the real screen"
    assert rest["organs_detected"] >= FLOOR_ORGANS, f"only {rest['organs_detected']} organs at rest"
    assert need["highK"] >= 0.6, f"needs_you highK {need['highK']:.3f}"
    assert need["mean_dL"] >= 2 * rest["mean_dL"]


def test_R9_a_still_INSIDE_the_idle_cpu_window_shows_the_field(m, raw, pixels):
    idle_on = re_.cpu_summary(re_.load_cpu_csv(raw / m["raw"]["cpu"]["idle_on"]))
    still = pixels["resting-idle"]
    assert idle_on["first_ts"] <= still["meta"]["taken_at"] <= idle_on["last_ts"], "the idle still was not taken during the idle window"
    assert still["metrics"]["organs_detected"] >= FLOOR_ORGANS, \
        f"{still['metrics']['organs_detected']} organs inside the idle window: idle CPU was measured with the field missing"
    assert still["metrics"]["p95_dL"] <= 0.05
    idle = re_.load_dump(raw / m["raw"]["idle_window"]["dom_dump"])
    assert len(idle["rows"]) >= 8 and m["perf"]["sessions"] == len(idle["rows"]), "8 sessions were open during the idle window"
    assert idle["state"] == "resting" and idle["html"].get("data-cf-state") == "resting"
    assert idle_on["first_ts"] <= idle["captured_at"] <= idle_on["last_ts"]


# ---- F4: performance ---------------------------------------------------------------------------------------------------

def _phase(raw: Path, rel: str) -> dict:
    s = re_.cpu_summary(re_.load_cpu_csv(raw / rel))
    assert s["window_s"] >= MIN_WINDOW_S, f"{rel}: only {s['window_s']:.1f} s sampled"
    assert s["max_gap_s"] <= MAX_GAP_S, f"{rel}: a {s['max_gap_s']:.1f} s hole in the sampler"
    assert s["pids"] >= 2, f"{rel}: {s['pids']} pid(s) sampled; renderer + GPU are at least two"
    return s


def test_R10_cpu_deltas_are_recomputed_from_the_sampler_csvs(m, raw):
    files = m["raw"]["cpu"]
    got = {k: _phase(raw, files[k]) for k in ("idle_on", "idle_off", "working_on", "working_off")}
    p = m["perf"]
    for phase in ("idle", "working"):
        for side in ("on", "off"):
            assert abs(got[f"{phase}_{side}"]["mean_pct"] - p[phase][f"{side}_pct"]) <= 0.01, \
                f"{phase}.{side}_pct: recomputed {got[f'{phase}_{side}']['mean_pct']:.3f}, manifest {p[phase][f'{side}_pct']}"
    assert got["idle_on"]["mean_pct"] - got["idle_off"]["mean_pct"] <= p["budget"]["idle_pp"]
    assert got["working_on"]["mean_pct"] - got["working_off"]["mean_pct"] <= p["budget"]["working_pp"]
    assert p["window_s"] <= min(g["window_s"] for g in got.values()) + 1.0, "the manifest claims a longer window than was sampled"


def test_R11_field_updates_per_second_come_from_the_css_sampler(m, raw):
    f = re_.field_summary(re_.load_field_csv(raw / m["raw"]["cpu"]["working_field"]))
    work = re_.cpu_summary(re_.load_cpu_csv(raw / m["raw"]["cpu"]["working_on"]))
    assert f["hz"] >= 8, f"the field sampler ran at {f['hz']:.1f} Hz (< 8)"
    assert f["span_s"] >= 30, f"the field sampler covered {f['span_s']:.1f} s"
    inside = work["first_ts"] - 1 <= f["first_ts"] and f["last_ts"] <= work["last_ts"] + 1
    assert inside, "the field sampler is outside the working CPU window"
    assert abs(f["updates_per_s"] - m["perf"]["working"]["field_updates_per_s"]) <= 0.05
    assert f["updates_per_s"] >= 4.0


# ---- F4: vision ------------------------------------------------------------------------------------------------------

def test_R12_vision_verdicts_are_parsed_from_the_raw_response_which_quotes_every_still(m, raw):
    text = (raw / m["vision"]["file"].removeprefix(RAW_ROOT + "/")).read_text()
    assert len(text) >= 300, "a critique, not three words"
    parsed = re_.parse_vision(text)
    assert parsed["model"].lower() == m["vision"]["model"].lower()
    assert parsed["verdicts"] == m["vision"]["verdicts"]
    judged = {s["sha256"] for s in m["capture"]["stills"]}
    assert len(judged) >= 5
    assert judged <= set(parsed["quoted_sha256"]), f"the response does not quote: {sorted(judged - set(parsed['quoted_sha256']))}"


# ---- the loaders reject what they must (no evidence needed) ------------------------------------------------------------

def test_R13_loaders_reject_malformed_raw_files(tmp_path):
    def w(name, text):
        p = tmp_path / name
        p.write_text(text)
        return p
    with pytest.raises(ValueError, match="header"):
        re_.load_cpu_csv(w("a.csv", "pid,time,pct\n1,1,1\n"))
    with pytest.raises(ValueError, match="unparsable"):
        re_.load_cpu_csv(w("b.csv", "pid,ts,cpu_pct\n1,x,1\n"))
    with pytest.raises(ValueError, match="plausible"):
        re_.load_cpu_csv(w("c.csv", "pid,ts,cpu_pct\n1,1,-3\n"))
    with pytest.raises(ValueError, match="backwards"):
        re_.load_cpu_csv(w("d.csv", "pid,ts,cpu_pct\n1,5,1\n1,4,1\n"))
    with pytest.raises(ValueError, match="no samples"):
        re_.load_cpu_csv(w("e.csv", "pid,ts,cpu_pct\n"))
    with pytest.raises(ValueError, match="sha256"):
        re_.load_field_csv(w("f.csv", "ts,css_sha256\n1,abc\n2,def\n"))
    with pytest.raises(ValueError, match="JSON"):
        re_.load_dump(w("g.json", "{not json"))
    with pytest.raises(ValueError, match="schema"):
        re_.load_dump(w("h.json", json.dumps({"schema": "other"})))
    with pytest.raises(ValueError, match="stored_id"):
        re_.load_dump(w("i.json", json.dumps({"schema": re_.DUMP_SCHEMA})))
    with pytest.raises(ValueError, match="rgb"):
        re_.parse_css_rgb("#336699")
    with pytest.raises(ValueError, match="verdict"):
        re_.parse_vision("model: x\nreadable_at_a_glance: yes\n")
    with pytest.raises(ValueError, match="more than once"):
        re_.parse_vision("model: x\nreadable_at_a_glance: yes\nreadable_at_a_glance: no\n"
                         "five_states_distinguishable: yes\nnot_distracting_at_rest: yes")
    with pytest.raises(ValueError, match="model"):
        re_.parse_vision("readable_at_a_glance: yes\nfive_states_distinguishable: yes\nnot_distracting_at_rest: yes")


def test_R14_region_rules_refuse_cherry_picked_measurement_areas():
    base = {"region": [0, 0, 1200, 800], "exclude": []}
    assert re_.region_ok(base, 1200, 800) is None
    assert "outside" in re_.region_ok({**base, "region": [100, 0, 1200, 800]}, 1200, 800)
    assert "cropped" in re_.region_ok({**base, "region": [0, 0, 400, 300]}, 1200, 800)
    assert "exclusions" in re_.region_ok({**base, "exclude": [[0, 0, 1200, 300]]}, 1200, 800)


def test_R15_cpu_and_field_summaries_do_the_arithmetic():
    rows = [(1, t, 2.0) for t in range(0, 61, 2)] + [(2, t, 1.0) for t in range(0, 61, 2)]
    s = re_.cpu_summary(sorted(rows, key=lambda r: r[1]))
    assert (s["mean_pct"], s["window_s"], s["pids"], s["max_gap_s"], s["samples"]) == (3.0, 60, 2, 2, 31)
    f = re_.field_summary([(i / 10, "a" * 64 if (i // 3) % 2 else "b" * 64) for i in range(101)])
    assert f["hz"] == pytest.approx(10.0) and f["updates_per_s"] == pytest.approx(3.3, abs=0.1)
