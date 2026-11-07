"""ACCEPTANCE CONTRACT PART — the raw-evidence loaders are strict and exact (locked; GREEN on its own, needs no evidence).

Boundary and rejection tests for tests/acceptance/raw_evidence.py: the recomputation in test_o7_part1_recompute.py is only as
good as these loaders, so each rule is pinned at its edge (mutation-tested, see contract/PARTS.md).
"""
from __future__ import annotations

import copy
import json

import pytest

from . import raw_evidence as re_

SHA = "a" * 64


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def good_dump() -> dict:
    row = {"data-cf-session": "S1", "data-cf-state": "resting", "swatch_circles": 12}
    return {"schema": re_.DUMP_SCHEMA, "stored_id": "S1", "state": "resting", "focused": True, "plugin_js_sha256": SHA,
            "captured_at": 1.5, "html": {"data-cf-state": "resting"}, "row": row, "rows": [row, {**row, "data-cf-session": None}],
            "strip": {"text": ""}, "composer": {"border_color": "rgb(1, 2, 3)", "ring_vars": {"--dt-composer-ring": "x"}},
            "transcript_messages": 0}


def good_meta() -> dict:
    return {"schema": re_.STILL_SCHEMA, "state": "resting-idle", "png_sha256": SHA, "taken_at": 3, "region": [0, 0, 10, 10],
            "exclude": [[0, 0, 1, 1]]}


# ---- _need ------------------------------------------------------------------------------------------------------------

def test_need_accepts_the_right_type_and_nothing_else():
    assert re_._need({"a": 1}, "a", int, "w") == 1
    assert re_._need({"a": 1.5}, "a", (int, float), "w") == 1.5
    assert re_._need({"a": True}, "a", bool, "w") is True
    for obj, kind in (({}, int), ({"a": "x"}, int), ({"a": True}, int), ({"a": True}, (int, float)), ({"a": 1}, bool), ({"a": 1}, str)):
        with pytest.raises(ValueError, match="missing or not"):
            re_._need(obj, "a", kind, "w")


# ---- dumps ------------------------------------------------------------------------------------------------------------

def test_a_good_dump_loads_with_its_rows(tmp_path):
    d = re_.load_dump(write(tmp_path, "d.json", json.dumps(good_dump())))
    assert d["row"] == {"data-cf-session": "S1", "data-cf-state": "resting", "swatch_circles": 12}
    assert [r["data-cf-session"] for r in d["rows"]] == ["S1", None]


@pytest.mark.parametrize("path", ["stored_id", "state", "focused", "plugin_js_sha256", "captured_at", "html", "strip", "composer", "row",
                                  "rows", "transcript_messages", "strip.text", "composer.border_color", "composer.ring_vars",
                                  "row.swatch_circles"])
def test_a_dump_missing_any_field_is_rejected(tmp_path, path):
    d = good_dump()
    node = d
    *parents, leaf = path.split(".")
    for k in parents:
        node = node[k]
    del node[leaf]
    with pytest.raises(ValueError, match="missing or not"):
        re_.load_dump(write(tmp_path, "d.json", json.dumps(d)))


@pytest.mark.parametrize("mutate,why", [
    (lambda d: d.update(state="sulking"), "unknown state"), (lambda d: d.update(plugin_js_sha256="abc"), "sha256"),
    (lambda d: d.update(rows=[1]), "every entry"), (lambda d: d.update(focused=1), "missing or not"),
    (lambda d: d.update(schema="cf2-dom-dump/0"), "schema")])
def test_a_dump_with_a_bad_value_is_rejected(tmp_path, mutate, why):
    d = copy.deepcopy(good_dump())
    mutate(d)
    with pytest.raises(ValueError, match=why):
        re_.load_dump(write(tmp_path, "d.json", json.dumps(d)))


def test_json_must_be_an_object(tmp_path):
    with pytest.raises(ValueError, match="expected a JSON object"):
        re_.load_json(write(tmp_path, "l.json", "[1]"))
    with pytest.raises(ValueError, match="unreadable"):
        re_.load_json(tmp_path / "nope.json")


# ---- still sidecars ---------------------------------------------------------------------------------------------------

def test_a_good_sidecar_loads_for_every_state(tmp_path):
    for state in (*re_.STATES, "resting-idle"):
        assert re_.load_still_meta(write(tmp_path, "m.json", json.dumps({**good_meta(), "state": state})))["state"] == state


@pytest.mark.parametrize("mutate,why", [
    (lambda m: m.update(schema="x"), "schema"), (lambda m: m.update(state="overview"), "unknown state"),
    (lambda m: m.update(png_sha256="zz"), "sha256"), (lambda m: m.pop("taken_at"), "missing or not"),
    (lambda m: m.update(region=[0, 0, 10]), "region"), (lambda m: m.update(region=[0, 0, 10, 10.5]), "region"),
    (lambda m: m.update(region=[0, 0, True, 10]), "region"), (lambda m: m.update(exclude=[[0, 0, 1]]), "exclude"),
    (lambda m: m.pop("exclude"), "missing or not"), (lambda m: m.pop("region"), "missing or not")])
def test_a_sidecar_with_a_bad_value_is_rejected(tmp_path, mutate, why):
    m = good_meta()
    mutate(m)
    with pytest.raises(ValueError, match=why):
        re_.load_still_meta(write(tmp_path, "m.json", json.dumps(m)))


# ---- region rules at their edges -----------------------------------------------------------------------------------------

def meta(region, exclude=()):
    return {"region": list(region), "exclude": [list(e) for e in exclude]}


def test_region_rules_at_the_edges():
    assert re_.region_ok(meta([0, 0, 100, 100]), 100, 100) is None
    assert re_.region_ok(meta([50, 0, 50, 100]), 100, 100) is None, "exactly half the image is allowed, touching the right edge"
    assert re_.region_ok(meta([0, 50, 100, 50]), 100, 100) is None, "touching the bottom edge"
    assert "cropped" in re_.region_ok(meta([0, 0, 99, 50]), 100, 100)
    assert "outside" in re_.region_ok(meta([1, 0, 100, 100]), 100, 100)
    assert "outside" in re_.region_ok(meta([0, 1, 100, 100]), 100, 100)
    assert "outside" in re_.region_ok(meta([-1, 0, 100, 100]), 100, 100)
    assert "outside" in re_.region_ok(meta([0, -1, 100, 100]), 100, 100)
    assert "outside" in re_.region_ok(meta([0, 0, 0, 100]), 100, 100)
    assert "outside" in re_.region_ok(meta([0, 0, 100, 0]), 100, 100)
    assert re_.region_ok(meta([0, 0, 100, 100], [[0, 0, 100, 25]]), 100, 100) is None, "exactly a quarter may be excluded"
    assert "exclusions" in re_.region_ok(meta([0, 0, 100, 100], [[0, 0, 100, 25], [0, 0, 1, 1]]), 100, 100)
    assert "25%" in re_.region_ok(meta([0, 0, 100, 100], [[0, 0, 100, 26]]), 100, 100)
    assert "covers 25%" in re_.region_ok(meta([0, 0, 50, 50]), 100, 100) and "(< 50%)" in re_.region_ok(meta([0, 0, 10, 10]), 100, 100)
    assert "cover 26%" in re_.region_ok(meta([0, 0, 100, 100], [[0, 0, 100, 26]]), 100, 100)
    assert re_.region_ok(meta([0, 0, 1, 1]), 1, 1) is None, "a one-pixel image's whole region is not 'outside'"
    assert re_.region_ok(meta([0, 0, 1, 100]), 1, 100) is None and re_.region_ok(meta([0, 0, 100, 1]), 100, 1) is None


# ---- css colour ---------------------------------------------------------------------------------------------------------

def test_css_rgb_parsing():
    assert re_.parse_css_rgb("rgb(1, 2, 3)") == (1, 2, 3, 1.0)
    assert re_.parse_css_rgb(" rgba(255,0,10, 0.5) ") == (255, 0, 10, 0.5)
    for bad in ("rgb(256, 0, 0)", "rgb(1,2)", "#fff", "rgb(1, 2, 3, x)", ""):
        with pytest.raises(ValueError):
            re_.parse_css_rgb(bad)


# ---- CPU CSV ------------------------------------------------------------------------------------------------------------

def test_cpu_csv_loads_and_rejects_at_the_edges(tmp_path):
    ok = re_.load_cpu_csv(write(tmp_path, "a.csv", "pid,ts,cpu_pct\n7,1.5,0\n8,1.5,2.5\n7,2.5,1\n"))
    assert ok == [(7, 1.5, 0.0), (8, 1.5, 2.5), (7, 2.5, 1.0)], "equal timestamps (several pids) and 0 % are fine"
    for i, row in enumerate(("0,1,1", "-1,1,1", "1,1,-0.5", "1,nan,1", "1,1,nan", "1,1,", ",1,1", "1.5,1,1"), start=1):
        with pytest.raises(ValueError, match="plausible|unparsable"):
            re_.load_cpu_csv(write(tmp_path, f"b{i}.csv", f"pid,ts,cpu_pct\n{row}\n"))
    unordered = re_.load_cpu_csv(write(tmp_path, "pids.csv", "pid,ts,cpu_pct\n8,1,1\n7,2,1\n"))
    assert unordered == [(8, 1.0, 1.0), (7, 2.0, 1.0)], "pid order is free"
    with pytest.raises(ValueError, match="backwards"):
        re_.load_cpu_csv(write(tmp_path, "c.csv", "pid,ts,cpu_pct\n1000,2,1\n1000,1.999,1\n"))
    with pytest.raises(ValueError, match="no samples"):
        re_.load_cpu_csv(write(tmp_path, "d.csv", "pid,ts,cpu_pct\n"))


def test_cpu_summary_arithmetic():
    s = re_.cpu_summary([(1, 10.0, 1.0), (2, 10.0, 2.0), (1, 12.0, 4.0), (2, 12.0, 0.0), (1, 15.0, 5.0), (2, 15.0, 1.0)])
    assert s == {"mean_pct": pytest.approx((3 + 4 + 6) / 3), "window_s": 5.0, "samples": 3, "max_gap_s": 3.0, "pids": 2,
                 "first_ts": 10.0, "last_ts": 15.0}
    one = re_.cpu_summary([(1, 10.0, 1.0)])
    assert one["window_s"] == 0 and one["max_gap_s"] == float("inf") and one["pids"] == 1 and one["samples"] == 1


# ---- field CSV ----------------------------------------------------------------------------------------------------------

def test_field_csv_loads_and_rejects_at_the_edges(tmp_path):
    h = "ts,css_sha256\n"
    assert re_.load_field_csv(write(tmp_path, "a.csv", h + f"1,{SHA}\n1,{SHA}\n")) == [(1.0, SHA), (1.0, SHA)], "two samples, equal ts ok"
    for i, body in enumerate((f"1,{SHA}\n", "", f"x,{SHA}\n2,{SHA}\n", f"1,{SHA[:-1]}\n2,{SHA}\n", f"1,\n2,{SHA}\n"), start=1):
        with pytest.raises(ValueError):
            re_.load_field_csv(write(tmp_path, f"b{i}.csv", h + body))
    with pytest.raises(ValueError, match="time order"):
        re_.load_field_csv(write(tmp_path, "c.csv", h + f"2,{SHA}\n1,{SHA}\n"))


def test_field_summary_arithmetic():
    rows = [(0.0, "a"), (0.5, "a"), (1.0, "b"), (1.5, "b"), (2.0, "a")]
    s = re_.field_summary(rows)
    assert s == {"span_s": 2.0, "hz": pytest.approx(2.0), "updates_per_s": pytest.approx(1.0), "first_ts": 0.0, "last_ts": 2.0}
    short = re_.field_summary([(5.0, "a"), (5.5, "b")])
    assert short["hz"] == pytest.approx(2.0) and short["updates_per_s"] == pytest.approx(2.0), "a span under one second still divides"
    flat = re_.field_summary([(5.0, "a"), (5.0, "b")])
    assert flat["hz"] == 0.0 and flat["updates_per_s"] == 0.0 and flat["span_s"] == 0


# ---- vision -------------------------------------------------------------------------------------------------------------

ALL_YES = "readable_at_a_glance: yes\nfive_states_distinguishable: yes\nnot_distracting_at_rest: yes\n"


def test_vision_parsing_is_case_insensitive_and_maps_yes_no():
    one, two = "1" * 64, "0" * 64
    p = re_.parse_vision("Model: Gemini X\nREADABLE_AT_A_GLANCE: YES\n  five_states_distinguishable : no \n"
                         f"not_distracting_at_rest: Yes\n{one} {two} {one}")
    assert p["model"] == "Gemini X"
    assert p["verdicts"] == {"readable_at_a_glance": True, "five_states_distinguishable": False, "not_distracting_at_rest": True}
    assert p["quoted_sha256"] == [two, one], "sorted, de-duplicated"


def test_vision_parsing_rejects_missing_duplicate_or_modelless():
    for key in re_.VERDICT_KEYS:
        text = "model: m\n" + ALL_YES.replace(f"{key}: yes\n", "")
        with pytest.raises(ValueError, match=key):
            re_.parse_vision(text)
        with pytest.raises(ValueError, match=f"{key} more than once"):
            re_.parse_vision("model: m\n" + ALL_YES + f"{key}: no\n")
    with pytest.raises(ValueError, match="model"):
        re_.parse_vision(ALL_YES)
    with pytest.raises(ValueError, match="verdict"):
        re_.parse_vision("model: m\nreadable_at_a_glance: maybe\n" + ALL_YES.split("\n", 1)[1])
