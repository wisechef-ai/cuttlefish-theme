"""ACCEPTANCE CONTRACT PART 2 — O7 bindings: toggled CPU windows, honest stills, contained paths.

Closes luna-parts L5, L6, M1, M2 (locked with the parts).

Adds to the raw-evidence schema (contract/PARTS-2.md; the part-1 files are locked, nothing there changes):
  manifest.raw.cpu_windows[idle_on|idle_off|working_on|working_off] =
      {file, dom_dump, roles: {pid: "renderer"|"gpu"|"main"}}
  manifest.raw.cpu_order = [window names in the order they were measured]
  manifest.capture.stills[i].dom_dump   (every MEASURED still, i.e. one with `meta`): the focused session's dump at capture time
  raw/dom/win.<name>.json (cf2-window-dump/1): {schema, window, plugin: "on"|"off", captured_at, html: {…}, rows: [{swatch_circles…}]}
L5  each CPU window's dump was taken inside the window; 'on' shows html[data-cf-state] + ≥ 1 swatch, 'off' shows no data-cf-* and no swatch;
    every window samples the same pid ROLES (renderer, gpu, optional main); windows do not overlap and cpu_order matches the timestamps.
L6  exclusion rects have positive size and lie inside the still; measured stills were taken with transcript_messages == 0.
M1  every path of the manifest resolves under evidence/v2/raw/ (no absolute path, no '..', no symlink out).
M2  a manifest still's state equals its sidecar's state; a measured state appears once.
"""
from __future__ import annotations

import json
import struct

import pytest

from . import raw_evidence as re_
from . import raw_evidence2 as re2
from .helpers import ROOT

MANIFEST = ROOT / "evidence" / "v2" / "manifest.json"
RAW_ROOT = re2.RAW_ROOT
KEY = {"idle_on": "idle_on", "idle_off": "idle_off", "working_on": "working_on", "working_off": "working_off"}


@pytest.fixture(scope="module")
def m() -> dict:
    assert MANIFEST.is_file(), f"{MANIFEST.relative_to(ROOT)} missing: run the real-Desktop harness (make evidence)"
    return json.loads(MANIFEST.read_text())


@pytest.fixture(scope="module")
def raw(m):
    root = ROOT / RAW_ROOT
    assert root.is_dir(), f"{RAW_ROOT}/ missing"
    return root


def png_size(p) -> tuple[int, int]:
    head = p.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{p} is not a PNG"
    return struct.unpack(">II", head[16:24])


# ---- the evidence -------------------------------------------------------------------------------------------------------

def test_B1_M1_every_manifest_path_stays_under_the_raw_tree(m, raw):
    assert re2.path_problems(raw, m) == []


def measured(m):
    return [s for s in m["capture"]["stills"] if "meta" in s]


def test_B2_M2_still_labels_match_their_sidecars_and_are_unique(m, raw):
    entries = measured(m)
    metas = [re_.load_still_meta(re2.contained(raw, s["meta"])) for s in entries]
    assert re2.label_problems(entries, metas) == []


def test_B3_L6_measured_stills_have_sane_exclusions_and_an_empty_transcript(m, raw):
    for s in measured(m):
        meta = re_.load_still_meta(re2.contained(raw, s["meta"]))
        w, h = png_size(re2.contained(raw, s["path"]))
        assert re2.rect_problems(meta, w, h) == [], s["path"]
        assert "dom_dump" in s, f"{s['path']}: no dom_dump to prove the transcript was empty"
        dump = re_.load_dump(re2.contained(raw, s["dom_dump"]))
        assert dump["transcript_messages"] == 0, f"{s['path']}: {dump['transcript_messages']} transcript messages were on screen"


def test_B4_L5_cpu_windows_are_bound_to_a_real_plugin_toggle(m, raw):
    spec = m["raw"].get("cpu_windows")
    assert isinstance(spec, dict) and set(spec) == set(re2.CPU_WINDOWS), "manifest.raw.cpu_windows must describe the four windows"
    spans, roles = {}, {}
    for name in re2.CPU_WINDOWS:
        w = spec[name]
        assert w["file"] == m["raw"]["cpu"][KEY[name]], f"{name}: cpu_windows.file differs from raw.cpu"
        s = re_.cpu_summary(re_.load_cpu_csv(re2.contained(raw, w["file"])))
        spans[name] = (s["first_ts"], s["last_ts"])
        assert set(w["roles"]) == {str(pid) for pid in {r[0] for r in re_.load_cpu_csv(re2.contained(raw, w["file"]))}}, \
            f"{name}: roles do not cover exactly the sampled pids"
        roles[name] = w["roles"]
        dump = re2.load_window_dump(re2.contained(raw, w["dom_dump"]))
        assert re2.toggle_problems(name, dump, *spans[name]) == []
    assert re2.role_problems(roles) == []
    assert re2.order_problems(spans, m["raw"]["cpu_order"]) == []


# ---- negative controls (no evidence needed) -----------------------------------------------------------------------------

def test_B5_containment_rejects_escapes(tmp_path):
    raw = tmp_path / "raw"
    (raw / "dom").mkdir(parents=True)
    (raw / "dom" / "a.json").write_text("{}")
    outside = tmp_path / "outside"
    outside.mkdir()
    (raw / "link").symlink_to(outside)
    assert re2.contained(raw, "dom/a.json") == (raw / "dom" / "a.json").resolve()
    assert re2.contained(raw, f"{RAW_ROOT}/dom/a.json") == (raw / "dom" / "a.json").resolve()
    for bad in ("../outside/x", "dom/../../outside", "/etc/passwd", "", "link/x", "dom/..", "..", "\\windows", "dom/\x00a"):
        with pytest.raises(ValueError):
            re2.contained(raw, bad)
    with pytest.raises(ValueError):
        re2.contained(raw, None)


def manifest(**over):
    m = {"raw": {"files": [{"path": "dom/a.json"}], "cpu": {"idle_on": "cpu/a.csv"}, "idle_window": {"dom_dump": "dom/i.json"}},
         "capture": {"sessions": [{"dom_dump": "dom/s.json"}], "stills": [{"path": f"{RAW_ROOT}/stills/r.png", "meta": "stills/r.json",
                                                                           "dom_dump": "dom/s.json"}]},
         "vision": {"file": f"{RAW_ROOT}/vision/response.txt"}}
    m.update(over)
    return m


def test_B6_path_problems_names_the_field(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    assert re2.path_problems(raw, manifest()) == []
    m = manifest()
    m["raw"]["cpu"]["idle_on"] = "../../etc/shadow"
    m["capture"]["stills"][0]["dom_dump"] = "/tmp/x.json"
    m["vision"]["file"] = "evidence/v2/other/response.txt"
    m["raw"]["cpu_windows"] = {"idle_on": {"file": "cpu/a.csv", "dom_dump": "../w.json"}}
    bad = re2.path_problems(raw, m)
    assert len(bad) == 4, bad
    assert any("raw.cpu.idle_on" in b for b in bad) and any("stills[0].dom_dump" in b for b in bad)
    assert any("vision.file" in b for b in bad) and any("cpu_windows.idle_on.dom_dump" in b for b in bad)


def test_B7_label_problems_catch_mislabels_and_duplicates():
    def e(state):
        return {"state": state}
    assert re2.label_problems([e("resting"), e("working")], [e("resting"), e("working")]) == []
    assert any("mislabel" in x or "sidecar" in x for x in re2.label_problems([e("working")], [e("resting")]))
    dup = re2.label_problems([e("resting"), e("resting")], [e("resting"), e("resting")])
    assert dup == ["state 'resting' is measured 2 times"]
    assert re2.label_problems([e("resting"), e("working")], [e("working"), e("resting")]) != []


def test_B8_rect_problems():
    assert re2.rect_problems({"exclude": [[0, 0, 100, 50], [0, 50, 100, 50]]}, 100, 100) == []
    cancel = re2.rect_problems({"exclude": [[0, 0, 100, 100], [0, 0, 100, -100]]}, 100, 100)
    assert len(cancel) == 1 and "non-positive" in cancel[0]
    for rect in ([0, 0, 0, 10], [0, 0, 10, 0], [-1, 0, 10, 10], [0, -1, 10, 10], [95, 0, 10, 10], [0, 95, 10, 10]):
        assert re2.rect_problems({"exclude": [rect]}, 100, 100), rect
    assert re2.rect_problems({"exclude": [[90, 90, 10, 10]]}, 100, 100) == [], "touching the edge is inside"


def window(plugin="on", at=5.0, state="working", swatches=1):
    return {"schema": re2.WINDOW_SCHEMA, "window": "x", "plugin": plugin, "captured_at": at,
            "html": {"data-cf-state": state} if state else {}, "rows": [{"swatch_circles": swatches}]}


def test_B9_toggle_problems_two_on_windows_labelled_on_off_fail():
    on = window("on")
    assert re2.toggle_problems("idle_on", on, 0, 10) == []
    assert re2.toggle_problems("idle_off", window("off", state=None, swatches=0), 0, 10) == []
    # the same 'on' dump submitted for an off-labelled window
    bad = re2.toggle_problems("idle_off", on, 0, 10)
    assert any("plugin 'on'" in b for b in bad) and any("'off' window shows the plugin" in b for b in bad)
    # an off dump submitted for an on-labelled window
    assert any("must show html[data-cf-state]" in b for b in re2.toggle_problems("idle_on", window("off", state=None, swatches=0), 0, 10))
    assert any("swatch" in b for b in re2.toggle_problems("idle_on", window("on", swatches=0), 0, 10))
    assert any("data-cf-state" in b for b in re2.toggle_problems("idle_on", window("on", state=None), 0, 10))
    assert any("outside the window" in b for b in re2.toggle_problems("idle_on", window("on", at=11), 0, 10))
    assert any("outside the window" in b for b in re2.toggle_problems("idle_on", window("on", at=-1), 0, 10))
    assert re2.toggle_problems("idle_on", window("on", at=0), 0, 10) == []
    assert re2.toggle_problems("idle_on", window("on", at=10), 0, 10) == []
    off_attr = window("off", state=None, swatches=0)
    off_attr["html"] = {"data-cf-foo": "1"}
    assert re2.toggle_problems("working_off", off_attr, 0, 10)


def test_B10_role_problems():
    ok = {n: {"1": "renderer", "2": "gpu"} for n in re2.CPU_WINDOWS}
    assert re2.role_problems(ok) == []
    assert re2.role_problems({**ok, "idle_off": {"7": "renderer", "8": "gpu"}}) == [], "pids differ between launches; roles must match"
    assert any("different pid roles" in b for b in re2.role_problems({**ok, "idle_off": {"7": "renderer", "8": "renderer"}}))
    assert any("different pid roles" in b for b in re2.role_problems({**ok, "idle_off": {"7": "renderer", "8": "gpu", "9": "main"}}))
    with_main = {n: {"1": "renderer", "2": "gpu", "3": "main"} for n in re2.CPU_WINDOWS}
    assert re2.role_problems(with_main) == []
    assert any("must include" in b for b in re2.role_problems({"a": {"1": "renderer"}}))
    assert any("must include" in b for b in re2.role_problems({"a": {"1": "renderer", "2": "gpu", "3": "utility"}}))


def test_B11_order_problems():
    spans = {"idle_on": (0, 10), "idle_off": (20, 30), "working_on": (40, 50), "working_off": (60, 70)}
    order = ["idle_on", "idle_off", "working_on", "working_off"]
    assert re2.order_problems(spans, order) == []
    assert any("timestamps say" in b for b in re2.order_problems(spans, list(reversed(order))))
    assert any("overlap" in b for b in re2.order_problems({**spans, "idle_off": (10, 30)}, order))
    assert any("overlap" in b for b in re2.order_problems({**spans, "idle_off": (5, 15)}, order))
    assert any("must list exactly" in b for b in re2.order_problems(spans, order[:3]))
    two_on = {**spans, "idle_off": spans["idle_on"]}
    assert any("overlap" in b for b in re2.order_problems(two_on, order)), "the same window submitted twice"


def test_B12_window_dump_loader_rejects(tmp_path):
    def w(d):
        p = tmp_path / "w.json"
        p.write_text(json.dumps(d))
        return p
    good = window()
    assert re2.load_window_dump(w(good))["plugin"] == "on"
    cases = (({**good, "schema": "x"}, "schema"), ({**good, "plugin": "maybe"}, "plugin"),
             ({**good, "captured_at": "now"}, "captured_at"), ({**good, "captured_at": True}, "captured_at"),
             ({**good, "html": []}, "html"), ({**good, "rows": {}}, "rows"))
    for bad, why in cases:
        with pytest.raises(ValueError, match=why):
            re2.load_window_dump(w(bad))
