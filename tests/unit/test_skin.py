"""Unit: cuttlefish.skin — one file, atomic, never selects, user edits survive."""

from __future__ import annotations

import yaml
from cuttlefish_theme.cuttlefish import skin


def test_install_is_atomic_and_idempotent(tmp_path):
    home = tmp_path / "home"
    target = skin.install(home)
    assert target == home / "skins" / "cuttlefish.yaml"
    assert target.read_bytes() == skin.skin_source().read_bytes()
    first = target.stat().st_mtime_ns
    assert skin.install(home) == target
    assert target.stat().st_mtime_ns == first, "an identical re-install writes nothing"
    assert sorted(p.name for p in (home / "skins").iterdir()) == ["cuttlefish.yaml"], "no .tmp leftovers"


def test_install_survives_a_stale_tmp(tmp_path):
    home = tmp_path / "home"
    (home / "skins").mkdir(parents=True)
    (home / "skins" / "cuttlefish.yaml.tmp").write_text("junk from a crashed write")
    skin.install(home)
    assert not (home / "skins" / "cuttlefish.yaml.tmp").exists()
    assert (home / "skins" / "cuttlefish.yaml").read_bytes() == skin.skin_source().read_bytes()


def test_install_makes_its_own_dirs(tmp_path):
    target = skin.install(tmp_path / "deep" / "home")
    assert target.is_file()


def test_uninstall_only_removes_what_is_ours(tmp_path):
    home = tmp_path / "home"
    assert skin.uninstall(home) is False, "nothing installed: no error, no effect"
    target = skin.install(home)
    target.write_text(target.read_text() + "\n# my tweak\n")
    assert skin.uninstall(home) is False, "a user-edited copy is theirs"
    assert target.is_file()
    target.write_bytes(skin.skin_source().read_bytes())
    assert skin.uninstall(home) is True
    assert not target.exists()


def test_the_skin_itself_is_static_and_safe():
    data = yaml.safe_load(skin.skin_source().read_text())
    assert data["name"] == "cuttlefish"
    assert set(data) <= {"name", "description", "colors", "spinner", "branding", "tool_prefix",
                         "tool_emojis", "banner_logo", "banner_hero"}
    for key in data["colors"]:
        assert "background" not in key.lower()
