"""Unit: the plugin loads on a Hermes runtime that has NO PyYAML (a real v0.23.0 gateway on Python 3.14).

Hermes core reads YAML through its own public module ``hermes_yaml``; PyYAML is not guaranteed. Our dev venv has PyYAML,
so an in-process test can never see a bare ``import yaml`` break. Each test here runs the load in a fresh interpreter in
which ``yaml`` is made un-importable (``sys.modules['yaml'] = None``), exactly as the host would see it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parents[2]

#: Loads the package the way the host does (repo root as ``cuttlefish_theme``), then the dashboard by path, then
#: ``register(ctx)`` with a fake ctx. Prints OK only if every step succeeded. ``sys.argv[1]`` is the repo root.
PROBE = textwrap.dedent(r"""
    import importlib.util, json, sys
    sys.modules["yaml"] = None  # a runtime without PyYAML
    root = sys.argv[1]
    sys.path[:0] = sys.argv[2:]  # extra import roots (a core stub), passed explicitly: -I ignores PYTHONPATH

    spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", root + "/__init__.py", submodule_search_locations=[root])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["cuttlefish_theme"] = pkg
    spec.loader.exec_module(pkg)

    class Ctx:
        def __init__(self):
            self.hooks, self.commands = [], []
        def register_hook(self, name, fn):
            self.hooks.append(name)
        def register_cli_command(self, name, **kw):
            self.commands.append(name)

    ctx = Ctx()
    pkg.register(ctx)
    assert len(ctx.hooks) == 5 and ctx.commands == ["cuttlefish"], (ctx.hooks, ctx.commands)

    dspec = importlib.util.spec_from_file_location("cf_probe_plugin_api", root + "/dashboard/plugin_api.py")
    api = importlib.util.module_from_spec(dspec)
    dspec.loader.exec_module(api)
    config = api.get_config()
    assert set(config) == {"settings", "warnings", "rev"}, config
    health = api.get_health()
    assert health["ok"] is True, health
    print("OK", json.dumps({"settings": config["settings"]["motion"], "warnings": config["warnings"]}))
""")


def _probe(tmp_path, extra_path=()):
    env = dict(os.environ, HERMES_HOME=str(tmp_path / "home"))
    return subprocess.run([sys.executable, "-I", "-c", PROBE, str(ROOT), *map(str, extra_path)],
                          capture_output=True, text=True, env=env, timeout=120)


def test_package_loads_and_registers_without_pyyaml(tmp_path):
    """The host's first import. Fails on any shipped module that does a bare ``import yaml``."""
    result = _probe(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK"), result.stdout + result.stderr


def test_config_is_read_live_through_core_hermes_yaml_without_pyyaml(tmp_path):
    """Core's parser is the one that runs on a Hermes install: a stub stands in for it (JSON is YAML)."""
    stub_dir = tmp_path / "core"
    stub_dir.mkdir()
    (stub_dir / "hermes_yaml.py").write_text(textwrap.dedent("""
        import json

        def safe_load(stream):
            return json.loads(stream if isinstance(stream, str) else stream.read())
    """))
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(json.dumps(
        {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "alive"}}}}}))
    result = _probe(tmp_path, extra_path=[stub_dir])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout[len("OK "):]) == {"settings": "alive", "warnings": []}
