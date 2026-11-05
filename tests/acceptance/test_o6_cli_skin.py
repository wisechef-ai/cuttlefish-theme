"""ACCEPTANCE CONTRACT — O6: the classic CLI gets a STATIC colour skin only (SPEC C10) (locked).

No background key (a skin background drives OSC-11, a full-terminal repaint), no per-cell `on #bg` art (the TUI parser
prints it literally: hotfix b371322), no desktop customCSS (the Desktop half owns the desktop). Installing it is an
explicit command, writes exactly one file, never selects it for the user, and the REAL core skin loader accepts it.
"""
from __future__ import annotations

import hashlib
import importlib
import re
import subprocess

import yaml

from .helpers import CORE, CORE_PYTHON, ROOT, need_core, plugin_package

SKIN = ROOT / "skins" / "cuttlefish.yaml"
ALLOWED_TOP = {"name", "description", "colors", "spinner", "branding", "tool_prefix", "tool_emojis", "banner_logo", "banner_hero"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield f"{path}.{k}".lstrip("."), k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")


def _hue(hex_: str) -> float:
    import colorsys
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def test_O6_1_static_skin_shape():
    data = yaml.safe_load(SKIN.read_text())
    assert data["name"] == "cuttlefish"
    assert set(data) <= ALLOWED_TOP, f"unexpected keys: {sorted(set(data) - ALLOWED_TOP)}"
    for path, key, value in _walk(data):
        assert "background" not in str(key).lower(), f"{path}: no background keys (OSC-11 repaint)"
        if isinstance(value, str) and str(key) in {"banner_logo", "banner_hero"}:
            assert not re.search(r"\bon\s+#", value), f"{path}: per-cell 'on #bg' art prints literally in the TUI"
    colors = data["colors"]
    assert {"ui_accent", "banner_border", "banner_title", "prompt", "input_rule"} <= set(colors)
    assert all(HEX.match(v) for v in colors.values()), colors
    for key in ("ui_accent", "banner_title", "input_rule", "session_label"):
        if key in colors:
            h = _hue(colors[key])
            assert not (15 <= h < 75), f"{key} {colors[key]} is amber/red: core's alarm colours are not identity"
    assert colors.get("ui_warn", "#ffa726") and colors.get("ui_error", "#ef5350"), "alarms keep their meaning"


def test_O6_2_install_writes_one_file_never_selects_it_and_uninstall_removes_only_ours(tmp_path):
    plugin_package()
    skin = importlib.import_module("cuttlefish_theme.cuttlefish.skin")
    home = tmp_path / "home"
    (home / "skins").mkdir(parents=True)
    (home / "skins" / "theirs.yaml").write_text("name: theirs\n")
    (home / "config.yaml").write_text("display:\n  skin: default\n")
    before_cfg = (home / "config.yaml").read_bytes()
    p = skin.install(home)
    assert p == home / "skins" / "cuttlefish.yaml"
    assert p.read_bytes() == SKIN.read_bytes()
    assert skin.install(home) == p, "idempotent"
    assert sorted(x.name for x in (home / "skins").iterdir()) == ["cuttlefish.yaml", "theirs.yaml"]
    assert (home / "config.yaml").read_bytes() == before_cfg, "installing never selects the skin (the user owns that)"
    skin.uninstall(home)
    assert sorted(x.name for x in (home / "skins").iterdir()) == ["theirs.yaml"]
    # a user-edited copy is theirs now: uninstall keeps it
    p = skin.install(home)
    p.write_text(p.read_text() + "\n# my tweak\n")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    skin.uninstall(home)
    assert p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == digest


def test_O6_3_the_real_core_skin_loader_accepts_it(tmp_path):
    need_core()
    home = tmp_path / "home"
    (home / "skins").mkdir(parents=True)
    (home / "skins" / "cuttlefish.yaml").write_bytes(SKIN.read_bytes())
    code = ("from hermes_cli.skin_engine import load_skin; s = load_skin('cuttlefish'); "
            "print(s.name); print(s.colors.get('ui_accent'))")
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "HERMES_HOME": str(home), "PYTHONPATH": str(CORE),
           "TMPDIR": "/tmp", "HERMES_DISABLE_LAZY_INSTALLS": "1"}
    r = subprocess.run([str(CORE_PYTHON), "-c", code], env=env, capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    name, accent = r.stdout.strip().splitlines()[-2:]
    assert name == "cuttlefish"
    assert accent == yaml.safe_load(SKIN.read_text())["colors"]["ui_accent"], "core loaded OUR colours, not a fallback"
