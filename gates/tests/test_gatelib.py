"""Pure-part tests for the G2/G5 instruments (contrast, OKLab/dE, Machado, manifest, answer parsing).

Reference values are published ones (WCAG 2.x, Ottosson OKLab, Machado 2009 table), not self-derived.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gatelib as gl  # noqa: E402
import g5lib  # noqa: E402


# ---- WCAG contrast -------------------------------------------------------------------------
def test_contrast_black_white_is_21():
    assert gl.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-6)


def test_contrast_is_symmetric_and_one_for_equal():
    assert gl.contrast_ratio("#336699", "#336699") == pytest.approx(1.0)
    assert gl.contrast_ratio("#336699", "#eeeeee") == pytest.approx(gl.contrast_ratio("#eeeeee", "#336699"))


def test_contrast_wcag_published_grey_boundary():
    # #767676 on white is the well-known smallest grey passing 4.5:1; #777777 is just under.
    assert gl.contrast_ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)
    assert gl.contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


def test_parse_hex_accepts_short_and_rejects_garbage():
    assert gl.parse_hex("#fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        gl.parse_hex("red")


# ---- OKLab / dE ----------------------------------------------------------------------------
@pytest.mark.parametrize("rgb,lab", [
    ((255, 255, 255), (1.0, 0.0, 0.0)),
    ((255, 0, 0), (0.627955, 0.224863, 0.125846)),
    ((0, 255, 0), (0.866440, -0.233888, 0.179498)),
    ((0, 0, 255), (0.452014, -0.032457, -0.311528)),
])
def test_oklab_matches_ottosson_reference(rgb, lab):
    got = gl.rgb_to_oklab(np.array([rgb], dtype=np.uint8))[0]
    assert got == pytest.approx(lab, abs=2e-4)


def test_oklch_hue_of_primaries():
    lch = gl.oklab_to_lch(gl.rgb_to_oklab(np.array([(255, 0, 0), (0, 255, 0), (0, 0, 255)], dtype=np.uint8)))
    assert lch[:, 2] == pytest.approx([29.23, 142.50, 264.05], abs=0.05)


def test_delta_e_ok_is_euclidean_in_oklab():
    a = np.array([0.5, 0.1, 0.0]); b = np.array([0.5, 0.1, 0.02])
    assert gl.delta_e_ok(a, b) == pytest.approx(0.02)


def test_nearest_pair_finds_worst_pair_and_matrix_is_symmetric():
    labs = np.array([[0.5, 0.0, 0.0], [0.9, 0.1, 0.1], [0.5, 0.0, 0.01], [0.2, -0.1, 0.1]])
    worst, (i, j), mat = gl.nearest_pair(labs)
    assert worst == pytest.approx(0.01)
    assert {i, j} == {0, 2}
    assert np.allclose(mat, mat.T) and mat[0, 0] == 0


def test_median_oklab_excludes_masked_pixels():
    tile = np.zeros((4, 4, 3), dtype=np.uint8); tile[:] = (200, 40, 40)
    tile[:2, :2] = (255, 255, 255)  # a "glyph" block that would drag a mean
    mask = np.zeros((4, 4), dtype=bool); mask[:2, :2] = True
    with_mask = gl.median_oklab(tile, mask)
    plain = gl.rgb_to_oklab(np.array([(200, 40, 40)], dtype=np.uint8))[0]
    assert with_mask == pytest.approx(plain, abs=1e-9)


# ---- Machado 2009 --------------------------------------------------------------------------
def test_machado_matrices_match_published_severity_1_table():
    assert gl.machado_matrix("protan") == pytest.approx(np.array([
        [0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]))
    assert gl.machado_matrix("deutan") == pytest.approx(np.array([
        [0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]))
    assert gl.machado_matrix("tritan") == pytest.approx(np.array([
        [1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]))


@pytest.mark.parametrize("kind", ["protan", "deutan", "tritan"])
def test_cvd_keeps_greys_and_white(kind):
    img = np.array([[[255, 255, 255], [128, 128, 128], [0, 0, 0]]], dtype=np.uint8)
    out = gl.simulate_cvd(img, kind)
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 2


def test_cvd_changes_saturated_red_and_is_uint8():
    img = np.array([[[255, 0, 0]]], dtype=np.uint8)
    out = gl.simulate_cvd(img, "deutan")
    assert out.dtype == np.uint8 and out.shape == img.shape
    assert out[0, 0, 0] < 200 and out[0, 0, 1] > 0   # red collapses toward olive/yellow-brown
    with pytest.raises(ValueError):
        gl.simulate_cvd(img, "nope")


# ---- manifest ------------------------------------------------------------------------------
def _entry(**kw):
    e = {"file": "tui/x.png", "host": "tui-terminator", "scale": "M", "state": "idle", "rung": "half",
         "depth": "truecolor", "cols": 120, "session_idx": 2, "sessions": [2], "frame_t": 0.0,
         "crop": [0, 0, 10, 10], "capture_log": "l.log"}
    e.update(kw)
    return e


def test_load_manifest_roundtrip_and_groups(tmp_path):
    m = {"schema": "cf2909.p1.manifest/1", "direction": "d-x", "entries": [
        _entry(frame_t=0.0), _entry(frame_t=0.5, file="tui/y.png"), _entry(state="working", frame_t=0.25, file="tui/z.png")]}
    p = tmp_path / "manifest.json"; p.write_text(json.dumps(m))
    man = gl.load_manifest(p)
    assert man.direction == "d-x" and man.root == tmp_path and len(man.entries) == 3
    groups = man.frame_groups()
    sizes = sorted(len(v) for v in groups.values())
    assert sizes == [1, 2]
    assert [e.frame_t for e in groups[next(k for k, v in groups.items() if len(v) == 2)]] == [0.0, 0.5]


@pytest.mark.parametrize("bad", [
    {"schema": "wrong", "direction": "d", "entries": []},
    {"schema": "cf2909.p1.manifest/1", "entries": []},
    {"schema": "cf2909.p1.manifest/1", "direction": "d", "entries": [{"file": "a.png"}]},
])
def test_load_manifest_rejects_bad(tmp_path, bad):
    p = tmp_path / "m.json"; p.write_text(json.dumps(bad))
    with pytest.raises(gl.ManifestError):
        gl.load_manifest(p)


# ---- G2 verdict arithmetic -----------------------------------------------------------------
def test_identity_check_flags_greys_and_alarm_arc():
    labs_grey = gl.rgb_to_oklab(np.array([[120, 120, 120], [121, 121, 121], [122, 122, 122]], dtype=np.uint8))
    r = gl.identity_check(labs_grey, threshold=0.020)
    assert not r["ok_delta"] and r["worst_pair"] < 0.020
    red = gl.rgb_to_oklab(np.array([[220, 40, 40]], dtype=np.uint8))
    assert gl.identity_check(red, 0.02)["alarm_arc_violations"] == [0]
    in_arc = gl.rgb_to_oklab(np.array([[60, 140, 200]], dtype=np.uint8))   # hue ~ 240
    assert gl.identity_check(in_arc, 0.02)["alarm_arc_violations"] == []
    grey_ok = gl.rgb_to_oklab(np.array([[120, 120, 120]], dtype=np.uint8))  # chroma < .03 is exempt (unknown)
    assert gl.identity_check(grey_ok, 0.02)["alarm_arc_violations"] == []


def test_static_proof_identical_and_different():
    a = np.zeros((4, 4, 3), np.uint8); b = a.copy(); c = a.copy(); c[0, 0] = 1
    assert gl.frames_identical([a, b]) and not gl.frames_identical([a, c])


def test_rendered_text_contrast_measures_glyph_vs_cell_bg():
    cell = np.zeros((23, 11, 3), np.uint8); cell[:] = (16, 16, 24)
    cell[8:14, 3:8] = (240, 240, 240)
    hi = gl.measure_cell_contrast(cell)
    assert hi > 10
    cell2 = np.zeros((23, 11, 3), np.uint8); cell2[:] = (72, 72, 72); cell2[8:14, 3:8] = (120, 120, 120)
    lo = gl.measure_cell_contrast(cell2)
    assert 1.8 < lo < 2.3


# ---- G5 answer parsing ---------------------------------------------------------------------
def test_parse_score_strict_json_and_fenced_and_wrapped():
    assert g5lib.parse_answer('{"score": 7.5, "reason": "x"}', "score").value == 7.5
    assert g5lib.parse_answer('```json\n{"score": 8}\n```', "score").value == 8
    assert g5lib.parse_answer('Sure! {"score": 6}', "score").value == 6


@pytest.mark.parametrize("txt", [
    "", "I can't help with that.", '{"score": "high"}', '{"score": 11}', '{"score": -1}', '{"score": 7', "[]", '{"scr": 7}',
    '{"score": true}', '{"score": NaN}',
])
def test_parse_score_invalid_is_marked_invalid_never_none(txt):
    r = g5lib.parse_answer(txt, "score")
    assert r.valid is False and r.value is None


def test_parse_label_normalises_and_rejects_unknown_label():
    assert g5lib.parse_answer('{"label": "Needs Input"}', "label").value == "needs input"
    assert g5lib.parse_answer('{"label": "error"}', "label").value == "error"
    assert g5lib.parse_answer('{"label": "banana"}', "label").valid is False


def test_parse_match_letter_range():
    assert g5lib.parse_answer('{"match": "c"}', "match").value == "C"
    assert g5lib.parse_answer('{"match": "ZZ"}', "match").valid is False
    assert g5lib.parse_answer('{"match": "Q"}', "match").valid is False   # only A..P exist


# ---- G5 scoring / thresholds ---------------------------------------------------------------
def test_aesthetic_verdict_median_and_floor():
    assert g5lib.aesthetic_verdict([7, 8, 7, 9])["pass"]
    assert not g5lib.aesthetic_verdict([7, 8, 7, 5.9])["pass"]       # one below 6 fails
    assert not g5lib.aesthetic_verdict([6, 6, 6, 6.5])["pass"]       # median < 7 fails
    assert not g5lib.aesthetic_verdict([8, 8, None])["pass"]         # invalid answer = FAIL, not skipped
    assert g5lib.aesthetic_verdict([7, 7, 6])["pass"]                # boundary: median 7, min 6


def test_legend_verdict_accuracy_and_input_error_swap():
    ok = [("idle", "idle")] * 8 + [("needs input", "needs input"), ("error", "error")]
    v = g5lib.legend_verdict(ok)
    assert v["pass"] and v["accuracy"] == 1.0 and v["input_error_confusions"] == 0
    swap = ok[:-2] + [("needs input", "error"), ("error", "needs input")] + [("idle", "idle")] * 20
    v2 = g5lib.legend_verdict(swap)
    assert not v2["pass"] and v2["input_error_confusions"] == 2
    exactly80 = [("idle", "idle")] * 8 + [("idle", "working")] * 2
    assert g5lib.legend_verdict(exactly80)["pass"]
    below = [("idle", "idle")] * 79 + [("idle", "working")] * 21
    assert not g5lib.legend_verdict(below)["pass"]
    assert not g5lib.legend_verdict([("idle", None)] * 10)["pass"]    # unparseable counts as wrong


def test_confusion_matrix_has_invalid_column_and_highlights_input_error():
    cm = g5lib.confusion_matrix([("needs input", "error"), ("error", "needs input"), ("idle", None)])
    assert cm["counts"]["needs input"]["error"] == 1 and cm["counts"]["idle"]["invalid"] == 1
    md = g5lib.confusion_markdown(cm)
    assert "**1**" in md and "INPUT" in md


def test_identity_verdict_14_of_16():
    assert g5lib.identity_verdict(["A"] * 14 + [None, "B"], ["A"] * 14 + ["A", "A"])["pass"]
    assert not g5lib.identity_verdict(["A"] * 13 + [None] * 3, ["A"] * 16)["pass"]


def test_seeded_shuffle_is_deterministic_and_seed_sensitive():
    items = list(range(30))
    assert g5lib.seeded_shuffle(items, 7) == g5lib.seeded_shuffle(items, 7)
    assert g5lib.seeded_shuffle(items, 7) != g5lib.seeded_shuffle(items, 8)
    assert items == list(range(30))


def test_round_counter_appends_and_flags_three_consecutive_fails(tmp_path):
    f = tmp_path / "g5_rounds.json"
    for ok in (False, False):
        g5lib.record_round(f, "d-a", ok, now="2026-10-07T00:00:00Z")
    assert not g5lib.record_round(f, "d-b", False, now="t")["kill_rule_triggered"]
    r = g5lib.record_round(f, "d-a", False, now="2026-10-07T01:00:00Z")
    assert r["consecutive_failing_rounds"] == 3 and r["kill_rule_triggered"]
    r2 = g5lib.record_round(f, "d-a", True, now="2026-10-07T02:00:00Z")
    assert r2["consecutive_failing_rounds"] == 0 and not r2["kill_rule_triggered"]
    assert len(json.loads(f.read_text())) == 5


FORBIDDEN = ("cuttlefish", "sepia", "chromatophore", "mantle", "idle ", "working", "review", "needs-you", "fault")


def test_prompts_contain_no_design_vocabulary_outside_legend_labels():
    prompts = Path(__file__).resolve().parents[1] / "g5_prompts"
    files = sorted(prompts.glob("*.txt"))
    assert {f.name for f in files} >= {"aesthetic_xl.txt", "aesthetic_ms.txt", "legend.txt", "identity.txt"}
    for f in files:
        txt = f.read_text().lower()
        for w in ("cuttlefish", "sepia", "chromatophore", "mantle", "needs-you", "fault", "iridophore"):
            assert w not in txt, f"{f.name} contains {w}"
        if f.name != "legend.txt":
            for w in ("idle", "working", "review", "error", "needs input"):
                assert w not in txt, f"{f.name} contains {w}"
