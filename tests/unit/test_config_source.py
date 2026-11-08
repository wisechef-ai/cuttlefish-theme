"""Unit: which core call reads our settings. Behavioural reads of the ACTIVE config go through core's read-only loader.

Core's ``read_user_config_raw`` is documented as legal only for write-back round-trips and raw-file diagnostics. Our
settings read is behavioural, so when the path we serve IS core's active ``config.yaml`` it must come from
``load_config_readonly()`` (merged, cached on the file signature, core's own parse-failure handling). Any other path (a
test home, a non-active profile) is a read-only raw read of a file we never write back.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest
from cuttlefish_theme.cuttlefish import liveconfig

ROOT = Path(__file__).parents[2]
DOC = {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "alive"}}}}}


def _read(path: Path) -> dict:
    """Core's documented shapes: a missing file reads as {}, a broken file raises, a non-mapping reads as {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


class FakeCore:
    """``hermes_cli.config`` with spies. Its active config is ``active``; ``load_config_readonly`` hands out one shared
    object, as core's cache does, so a caller that mutates it would corrupt later reads (the test checks we do not)."""

    def __init__(self, active: Path):
        self.active = active
        self.raw_calls: list[Path] = []
        self.readonly_calls = 0
        self._shared: dict | None = None

    def modules(self) -> dict:
        pkg = types.ModuleType("hermes_cli")
        pkg.__path__ = []
        config = types.ModuleType("hermes_cli.config")
        config.get_config_path = lambda: self.active / "config.yaml"
        config.get_process_hermes_home = lambda: self.active

        def read_user_config_raw(config_path=None):
            self.raw_calls.append(Path(config_path))
            return _read(config_path)

        def load_config_readonly():
            self.readonly_calls += 1
            if self._shared is None:
                try:
                    self._shared = _read(self.active / "config.yaml")
                except ValueError:  # core: a broken file falls back to defaults, with its own warning
                    self._shared = {}
            return self._shared

        config.read_user_config_raw = read_user_config_raw
        config.load_config_readonly = load_config_readonly
        pkg.config = config
        return {"hermes_cli": pkg, "hermes_cli.config": config}


@pytest.fixture
def core(tmp_path, monkeypatch):
    fake = FakeCore(tmp_path / "active")
    fake.active.mkdir()
    for name, mod in fake.modules().items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setitem(sys.modules, "yaml", None)  # the host need not have PyYAML
    return fake


def _write(path: Path, doc) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


MERGED = {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "off"}}}}}


def test_the_active_config_is_read_through_load_config_readonly(core, tmp_path):
    _write(core.active / "config.yaml", DOC)  # disk says alive ...
    core._shared = MERGED                      # ... core's merged view says off: we must serve core's view
    assert liveconfig.read_raw_settings(core.active) == ({"motion": "off"}, [])
    assert core.readonly_calls == 1
    assert set(core.raw_calls) <= {core.active / "config.yaml"}, \
        "the raw reader may only run as the parse-check diagnostic on the active file, never to read settings"


def test_another_home_is_read_through_the_raw_reader_only(core, tmp_path):
    other = _write(tmp_path / "other" / "config.yaml", DOC).parent
    assert liveconfig.read_raw_settings(other) == ({"motion": "alive"}, [])
    assert core.raw_calls == [other / "config.yaml"]
    assert core.readonly_calls == 0


def test_resolve_live_without_a_home_reads_the_active_config(core):
    _write(core.active / "config.yaml", DOC)
    core._shared = MERGED
    settings, warnings = liveconfig.resolve_live()
    assert settings["motion"] == "off" and warnings == []
    assert core.readonly_calls == 1


def test_the_settings_we_keep_are_a_copy_of_core_s_shared_dict(core):
    _write(core.active / "config.yaml", DOC)
    raw, _ = liveconfig.read_raw_settings(core.active)
    raw["motion"] = "off"
    raw["extra"] = 1
    again, _ = liveconfig.read_raw_settings(core.active)
    assert again == {"motion": "alive"}, "mutating our copy must not corrupt core's cached config"


def test_a_broken_active_config_still_warns_once_though_core_falls_back(core):
    (core.active).mkdir(exist_ok=True)
    (core.active / "config.yaml").write_text("{ not json")
    raw, warnings = liveconfig.read_raw_settings(core.active)
    assert raw is None
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]


def test_an_active_config_without_our_entry_is_not_a_warning(core):
    _write(core.active / "config.yaml", {"model": "x"})
    assert liveconfig.read_raw_settings(core.active) == (None, [])


def test_the_no_pyyaml_probe_still_loads_with_core_present(tmp_path):
    """Keep the host-load probe honest with core's door: the package loads and reads the active config."""
    probe = textwrap.dedent(r"""
        import importlib.util, json, sys
        from pathlib import Path
        sys.modules["yaml"] = None
        root = sys.argv[1]
        active = Path(sys.argv[2])
        import types
        hc = types.ModuleType("hermes_cli"); hc.__path__ = []
        cfg = types.ModuleType("hermes_cli.config")
        cfg.get_config_path = lambda: active / "config.yaml"
        cfg.get_process_hermes_home = lambda: active
        cfg.read_user_config_raw = lambda config_path=None: {}
        cfg.load_config_readonly = lambda: json.loads((active / "config.yaml").read_text())
        hc.config = cfg
        sys.modules["hermes_cli"] = hc; sys.modules["hermes_cli.config"] = cfg
        spec = importlib.util.spec_from_file_location("cuttlefish_theme", root + "/__init__.py",
                                                      submodule_search_locations=[root])
        pkg = importlib.util.module_from_spec(spec); sys.modules["cuttlefish_theme"] = pkg
        spec.loader.exec_module(pkg)
        settings, warnings = pkg.cuttlefish.liveconfig.resolve_live()
        print("OK", settings["motion"], warnings)
    """)
    active = tmp_path / "active"
    active.mkdir()
    (active / "config.yaml").write_text(json.dumps(DOC))
    result = subprocess.run([sys.executable, "-I", "-c", probe, str(ROOT), str(active)],
                            capture_output=True, text=True, env=dict(os.environ), timeout=120)
    assert result.returncode == 0 and result.stdout.startswith("OK alive"), result.stderr + result.stdout


@pytest.mark.skipif(not os.environ.get("HERMES_CORE"), reason="set HERMES_CORE to a hermes-core checkout to run")
def test_real_core_sees_a_live_edit_of_the_active_config(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(os.environ["HERMES_CORE"])
    for name in [m for m in list(sys.modules) if m == "hermes_cli" or m.startswith("hermes_cli.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text("plugins:\n  entries:\n    cuttlefish-theme:\n      settings:\n        motion: alive\n")
    assert liveconfig.resolve_live()[0]["motion"] == "alive"
    # quoted: an unquoted off is a YAML 1.1 boolean
    (home / "config.yaml").write_text("plugins:\n  entries:\n    cuttlefish-theme:\n      settings:\n        motion: \"off\"\n")
    assert liveconfig.resolve_live()[0]["motion"] == "off", "core's cache keys on the file signature: an edit applies"
    (home / "config.yaml").write_text("plugins: [unclosed\n")  # broken: core falls back, we still warn once
    settings, warnings = liveconfig.resolve_live()
    assert settings["motion"] == "off", "core serves its last-known-good copy of the file"
    assert [(w["path"], w["code"]) for w in warnings] == [("config", "type")]
