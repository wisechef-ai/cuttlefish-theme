"""Unit: cuttlefish.liveconfig — reading config.yaml live, degrading never raising."""

from __future__ import annotations

import yaml
from cuttlefish_theme.cuttlefish import liveconfig


def write_config(home, doc):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump(doc))
    return home


def test_missing_file_is_an_empty_config(tmp_path):
    raw, warnings = liveconfig.read_raw_settings(tmp_path)
    assert raw is None and warnings == []


def test_broken_yaml_degrades_with_one_warning(tmp_path):
    (tmp_path / "config.yaml").write_text(":: not yaml ::\n  - [")
    raw, warnings = liveconfig.read_raw_settings(tmp_path)
    assert raw is None
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]


def test_odd_shapes_read_as_empty(tmp_path):
    for text in ("plugins:\n", "plugins: 3\n", "plugins:\n  entries: [1]\n",
                 "plugins:\n  entries:\n    cuttlefish-theme: flat\n",
                 "plugins:\n  entries:\n    cuttlefish-theme:\n      settings:\n"):
        (tmp_path / "config.yaml").write_text(text)
        raw, warnings = liveconfig.read_raw_settings(tmp_path)
        assert raw in (None, {}, "") and warnings == [], text


def test_our_entry_is_dug_out(tmp_path):
    write_config(tmp_path, {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "off"}},
                                                   "other": {"settings": {"motion": "alive"}}}}})
    assert liveconfig.read_raw_settings(tmp_path)[0] == {"motion": "off"}


def test_resolve_live_merges_load_and_validation_warnings(tmp_path, monkeypatch):
    write_config(tmp_path, {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "wild", "zap": 1}}}}})
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    settings, warnings = liveconfig.resolve_live()
    assert settings["motion"] == "still"
    assert [(w["path"], w["code"]) for w in warnings] == [("motion", "enum"), ("zap", "unknown")]


def test_plugin_version_matches_the_manifest():
    manifest = yaml.safe_load(open("plugin.yaml").read())
    assert liveconfig.plugin_version() == str(manifest["version"]) == "2.0.0"


def test_hermes_home_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert liveconfig.hermes_home() == tmp_path
    assert liveconfig.config_path() == tmp_path / "config.yaml"


def test_hermes_home_last_resort_is_dot_hermes(tmp_path, monkeypatch):
    """No core, no env: the documented default ~/.hermes (never a raise)."""
    import pathlib
    import sys
    monkeypatch.setitem(sys.modules, "hermes_cli.config", None)  # the core door refuses
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    assert liveconfig.hermes_home() == tmp_path / ".hermes"


def test_resolve_live_honors_an_explicit_home(tmp_path, monkeypatch):
    served = write_config(tmp_path / "served", {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "off"}}}}})
    elsewhere = tmp_path / "elsewhere"  # the process's own home points elsewhere
    elsewhere.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(elsewhere))
    settings, warnings = liveconfig.resolve_live(served)
    assert settings["motion"] == "off" and warnings == []
