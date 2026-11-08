"""Unit: cuttlefish.liveconfig's YAML reader — core's hermes_yaml, else PyYAML, else the unreadable default.

Which library answers is decided by what can be imported, so each path is pinned by hiding the other modules in
``sys.modules`` (``None`` makes ``import`` raise ImportError). The real core module runs only when ``HERMES_CORE``
names a hermes-core checkout (its ruamel dependency must be installed); the stub stands in otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import types

import pytest
import yaml as pyyaml
from cuttlefish_theme.cuttlefish import liveconfig

SETTINGS_DOC = {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "alive"}}}}}


def _stub_hermes_yaml(calls):
    """A faithful stand-in for core's ``hermes_yaml.safe_load``: same name and signature, invalid input raises."""
    mod = types.ModuleType("hermes_yaml")

    def safe_load(stream):
        calls.append(True)
        return json.loads(stream if isinstance(stream, str) else stream.read())

    mod.safe_load = safe_load
    return mod


def _write(home, text):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(text)
    return home


def test_core_hermes_yaml_is_preferred_and_reads_the_config(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "hermes_yaml", _stub_hermes_yaml(calls))
    home = _write(tmp_path, json.dumps(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])
    assert calls, "the host's parser answers first"


def test_pyyaml_reads_the_config_when_core_is_absent(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_yaml", None)
    home = _write(tmp_path, pyyaml.safe_dump(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])


def test_neither_parser_degrades_to_the_unreadable_default_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_yaml", None)
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = _write(tmp_path, pyyaml.safe_dump(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])
    settings, warnings = liveconfig.resolve_live(home)
    assert settings["motion"] == "still"
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]
    assert liveconfig.plugin_version() == ""


def test_invalid_yaml_through_core_hermes_yaml_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_yaml", _stub_hermes_yaml([]))
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = _write(tmp_path, ":: not yaml ::\n  - [")
    raw, warnings = liveconfig.read_raw_settings(home)
    assert raw is None
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]


def test_invalid_yaml_through_pyyaml_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_yaml", None)
    home = _write(tmp_path, "a: [1, 2\nb: : :\n")
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])


def test_nesting_bomb_is_unreadable_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_yaml", None)
    home = _write(tmp_path, "[" * 100000)
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])


@pytest.mark.skipif(not os.environ.get("HERMES_CORE"), reason="set HERMES_CORE to a hermes-core checkout to run")
def test_the_real_core_hermes_yaml_parses_and_fails_as_we_expect(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(os.environ["HERMES_CORE"])
    monkeypatch.delitem(sys.modules, "hermes_yaml", raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = _write(tmp_path, "plugins:\n  entries:\n    cuttlefish-theme:\n      settings:\n        motion: alive\n")
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])
    bad = _write(tmp_path / "bad", "a: [1, 2\nb: : :\n")
    assert liveconfig.read_raw_settings(bad) == (None, [liveconfig._UNREADABLE])
