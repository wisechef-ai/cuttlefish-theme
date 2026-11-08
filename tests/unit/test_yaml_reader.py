"""Unit: cuttlefish.liveconfig's YAML reader — core's public door, else PyYAML, else the unreadable default.

Which reader answers is decided by what can be imported, so each path is pinned by hiding the other modules in
``sys.modules`` (``None`` makes ``import`` raise ImportError). The real core runs only when ``HERMES_CORE`` names a
hermes-core checkout (its own dependencies must be installed); the stub stands in otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest
import yaml as pyyaml
from cuttlefish_theme.cuttlefish import liveconfig

SETTINGS_DOC = {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "alive"}}}}}


def _stub_core(calls):
    """A faithful stand-in for ``hermes_cli.config.read_user_config_raw``: same name and signature, same contract
    (a missing file reads as ``{}``, a parse error raises, a non-mapping reads as ``{}``). JSON is YAML."""
    pkg = types.ModuleType("hermes_cli")
    pkg.__path__ = []
    config = types.ModuleType("hermes_cli.config")

    def read_user_config_raw(config_path=None):
        calls.append(config_path)
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        return data if isinstance(data, dict) else {}

    config.read_user_config_raw = read_user_config_raw
    pkg.config = config
    return {"hermes_cli": pkg, "hermes_cli.config": config}


def _hide_core(monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_cli", None)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", None)


def _use_core(monkeypatch, calls):
    for name, mod in _stub_core(calls).items():
        monkeypatch.setitem(sys.modules, name, mod)


def _write(home, text):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(text)
    return home


def test_core_is_the_reader_when_present(tmp_path, monkeypatch):
    calls = []
    _use_core(monkeypatch, calls)
    monkeypatch.setitem(sys.modules, "yaml", None)  # the host need not have PyYAML at all
    home = _write(tmp_path, json.dumps(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])
    assert calls == [home / "config.yaml"], "the host's own door answers, with the explicit path"


def test_pyyaml_reads_the_config_when_core_is_absent(tmp_path, monkeypatch):
    _hide_core(monkeypatch)
    home = _write(tmp_path, pyyaml.safe_dump(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])


def test_neither_reader_degrades_to_the_unreadable_default_and_never_raises(tmp_path, monkeypatch):
    _hide_core(monkeypatch)
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = _write(tmp_path, pyyaml.safe_dump(SETTINGS_DOC))
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])
    settings, warnings = liveconfig.resolve_live(home)
    assert settings["motion"] == "still"
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]
    assert liveconfig.plugin_version() == ""


def test_invalid_yaml_through_core_is_unreadable(tmp_path, monkeypatch):
    _use_core(monkeypatch, [])
    home = _write(tmp_path, ":: not yaml ::\n  - [")
    raw, warnings = liveconfig.read_raw_settings(home)
    assert raw is None
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]


def test_invalid_yaml_through_pyyaml_is_unreadable(tmp_path, monkeypatch):
    _hide_core(monkeypatch)
    home = _write(tmp_path, "a: [1, 2\nb: : :\n")
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])


def test_nesting_bomb_is_unreadable_not_a_crash(tmp_path, monkeypatch):
    _hide_core(monkeypatch)
    home = _write(tmp_path, "[" * 100000)
    assert liveconfig.read_raw_settings(home) == (None, [liveconfig._UNREADABLE])


def test_a_file_that_cannot_be_read_is_an_absent_config(tmp_path, monkeypatch):
    _hide_core(monkeypatch)
    (tmp_path / "config.yaml").mkdir()  # a directory where the file should be: OSError, not a parse problem
    assert liveconfig.read_raw_settings(tmp_path) == (None, [])


@pytest.mark.skipif(not os.environ.get("HERMES_CORE"), reason="set HERMES_CORE to a hermes-core checkout to run")
def test_the_real_core_reader_parses_and_fails_as_we_expect(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(os.environ["HERMES_CORE"])
    for name in [m for m in list(sys.modules) if m == "hermes_cli" or m.startswith("hermes_cli.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = _write(tmp_path, "plugins:\n  entries:\n    cuttlefish-theme:\n      settings:\n        motion: alive\n")
    assert liveconfig.read_raw_settings(home) == ({"motion": "alive"}, [])
    bad = _write(tmp_path / "bad", "a: [1, 2\nb: : :\n")
    assert liveconfig.read_raw_settings(bad) == (None, [liveconfig._UNREADABLE])
