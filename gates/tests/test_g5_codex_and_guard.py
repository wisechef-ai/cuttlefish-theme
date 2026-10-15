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
