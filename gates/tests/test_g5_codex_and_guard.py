"""Codex backend image delivery (P1 G5 2026-10-15: every codex answer was blind) and the anchor-probe blindness guard."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g5  # noqa: E402
import g5backends  # noqa: E402
import g5cache  # noqa: E402


@pytest.fixture
def item_png(tmp_path):
    p = tmp_path / "renders" / "g5_raw" / "images" / "legend-M-plain-M-half-tc-120-working-t000.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\x89PNG-fake-bytes")
    return p


def _fake_codex(seen):
    def run(cmd, input, cwd, **kw):
        img = Path(cmd[cmd.index("-i") + 1])
        seen.update(cmd=cmd, cwd=cwd, prompt=input, img=img, img_ok=img.is_file(), img_bytes=img.read_bytes() if img.is_file() else None)
        Path(cmd[cmd.index("-o") + 1]).write_text('{"label": "working"}')
        return subprocess.CompletedProcess(cmd, 0, "", "warning: Codex's Linux sandbox uses bubblewrap and needs access to create user namespaces.")
    return run


def test_codex_gets_a_readable_absolute_image_even_from_a_relative_path(item_png, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                   # the 2026-10-15 failure: relative path + codex cwd = temp dir
    seen = {}
    rel = item_png.relative_to(tmp_path)
    assert g5backends.codex_backend(rel, "PROMPT", run=_fake_codex(seen)) == '{"label": "working"}'
    assert seen["img"].is_absolute() and seen["img_ok"] and seen["img_bytes"] == item_png.read_bytes()
    assert seen["img"].parent == Path(seen["cwd"])               # inside codex's own working dir: always readable there
    assert seen["prompt"] == "PROMPT"


def test_codex_never_sees_the_item_file_name(item_png):
    seen = {}
    g5backends.codex_backend(item_png, "P", run=_fake_codex(seen))
    assert seen["img"].name == g5backends.CODEX_IMAGE_NAME        # codex writes <image path="..."> into the prompt
    joined = " ".join(seen["cmd"])
    for leak in ("working", "legend", "g5_raw", item_png.stem):
        assert leak not in joined


def test_codex_missing_image_is_a_transport_error_and_no_call(tmp_path):
    called = []
    with pytest.raises(g5backends.TransportError, match="image not found"):
        g5backends.codex_backend(tmp_path / "nope.png", "P", run=lambda *a, **k: called.append(1))
    assert called == []


def test_codex_nonzero_exit_is_a_transport_error(item_png):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: You've hit your usage limit.")
    with pytest.raises(g5backends.TransportError, match="usage limit"):
        g5backends.codex_backend(item_png, "P", run=run)


def test_codex_image_flag_is_never_followed_by_the_prompt_marker(tmp_path):
    cmd = g5backends.codex_cmd(tmp_path / "image.png", tmp_path / "out.txt")
    i = cmd.index("-i")
    assert cmd[i + 2].startswith("-") and cmd[i + 2] != "-"       # -i is variadic: a bare '-' after it is read as a 2nd image
    assert cmd[-1] == "-"


def test_nemotron_is_its_own_lane_on_hercules(monkeypatch):
    assert g5backends.resolve("nemotron") is g5backends.nemotron_backend
    assert g5backends.model_id("nemotron") == "nemotron-3.5-super-vl"
    monkeypatch.setenv("G5_NEMOTRON_MODEL", "other-vl")
    c = g5backends.nemotron_config()
    assert c.model == "other-vl" and c.key_name == "HERCULES_API_KEY" and c.url == g5backends.qwen_config().url
    assert g5backends.cache_model("nemotron").startswith("other-vl|") and "nemotron" in g5backends.label("nemotron")


def _r(v, valid=True, cached=False):
    return {"value": v, "valid": valid, "transport_error": "", "parse_error": "" if valid else "unparseable", "cached": cached}


@pytest.mark.parametrize("rows, ok", [
    ([_r(9), _r(9), _r(8), _r(9), _r(9), _r(8)], True),
    ([_r(7), _r(7), _r(7)], True),                                  # the floor itself passes (frozen >= 7)
    ([_r(0)] * 6, False),                                           # the 2026-10-15 codex signature
    ([_r(6), _r(7), _r(6)], False),
    ([_r(9), _r(9), _r(None, valid=False)], False),                 # any invalid anchor answer fails the probe
    ([], False),
])
def test_anchor_probe_floor(rows, ok):
    p = g5.anchor_probe(rows)
    assert p["ok"] is ok and p["floor"] == 7.0


def test_staged_cache_commits_or_discards(tmp_path):
    c = g5cache.Cache(tmp_path)
    s = g5cache.Staged(c)
    s.put("ab" + "0" * 62, "x")
    assert s.get("ab" + "0" * 62) == "x" and c.get("ab" + "0" * 62) is None
    assert s.discard() == 1 and s.get("ab" + "0" * 62) is None
    s.put("cd" + "0" * 62, "y")
    assert s.commit() == 1 and c.get("cd" + "0" * 62) == "y"
    off = g5cache.Staged(g5cache.Cache(tmp_path, enabled=False))
    off.put("ef" + "0" * 62, "z")
    assert off.commit() == 0


# --- family check: a model id is not a family (2026-10-16: hercules served ONE checkpoint under every id) ------------------------

HERCULES_MODELS_20261016 = {"object": "list", "data": [
    {"id": m, "root": "/home/adam/models/Nemotron-3.5-Super-VL-120B-A12B-NVFP4"}
    for m in ("nemotron-3.5-super-vl", "local-llm", "qwen3.8-27b-heretic", "superqwen3.8-27b")]}


def test_served_identity_reads_the_root_not_the_alias(monkeypatch):
    monkeypatch.setenv("HERCULES_API_KEY", "k")
    fetch = lambda url, key: HERCULES_MODELS_20261016
    assert g5backends.served_identity("qwen", fetch) == g5backends.served_identity("nemotron", fetch) == "hercules:Nemotron-3.5-Super-VL-120B-A12B-NVFP4"


def test_served_identity_distinguishes_a_real_second_checkpoint(monkeypatch):
    monkeypatch.setenv("HERCULES_API_KEY", "k")
    two = {"data": [{"id": "qwen3.8-27b-heretic", "root": "/m/Qwen3.8-27B"}, {"id": "nemotron-3.5-super-vl", "root": "/m/Nemotron-3.5"}]}
    fetch = lambda url, key: two
    assert g5backends.served_identity("qwen", fetch) != g5backends.served_identity("nemotron", fetch)


def test_unserved_or_unreachable_model_is_an_instrument_error(monkeypatch):
    monkeypatch.setenv("HERCULES_API_KEY", "k")
    with pytest.raises(g5backends.TransportError, match="not served"):
        g5backends.served_identity("qwen", lambda url, key: {"data": [{"id": "other", "root": "/m/x"}]})

    def down(url, key):
        raise OSError("connection refused")
    with pytest.raises(g5backends.TransportError, match="cannot ask"):
        g5backends.served_identity("nemotron", down)


def test_codex_and_glm_identities_need_no_network():
    assert g5backends.served_identity("codex").startswith("openai:codex")
    assert g5backends.served_identity("glm").startswith("zai:")


def test_family_check_refuses_two_lanes_on_one_checkpoint():
    with pytest.raises(g5.SameWeights, match="same model"):
        g5.family_check(["qwen", "nemotron"], identify=lambda n: "hercules:Nemotron")
    assert g5.family_check(["nemotron", "codex"], identify=lambda n: n) == {"nemotron": "nemotron", "codex": "codex"}


def test_run_refuses_same_weights_before_any_call(tmp_path):
    calls = []

    def fn(png, prompt):
        calls.append(png)
        return '{"score": 9}'
    with pytest.raises(g5.SameWeights):
        g5.run(tmp_path / "no-manifest-needed.json", {"qwen": fn, "nemotron": fn}, rounds_file=None, identify=lambda n: "hercules:same")
    assert calls == []


def test_default_pair_is_two_distinct_families_by_construction():
    names = g5backends.DEFAULT_BACKENDS.split(",")
    assert len(names) == 2 and not set(names) <= set(g5backends.HERCULES_LANES), "both default lanes on hercules = one checkpoint today"
