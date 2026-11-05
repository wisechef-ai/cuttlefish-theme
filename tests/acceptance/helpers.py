"""ACCEPTANCE CONTRACT — shared helpers for tests/acceptance (locked).

Never touches the live install: every Hermes run gets a throwaway HERMES_HOME, an explicit interpreter, and no
inherited environment. CF_STRICT=1 (set by `make contract`) turns "Hermes not available" into a FAILURE.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get("CF_HERMES_CORE", "/home/adam/repos/hackathon/hermes-core"))
CORE_PYTHON = Path(os.environ.get(
    "CF_HERMES_PYTHON",
    "/home/adam/.hermes/installs/249e8deaf2c7285a/environments/2a158adf8eb9433e9c3ec7634cd1c9e4/venv/bin/python"))
LIVE_HOME = Path.home() / ".hermes"
STRICT = os.environ.get("CF_STRICT") == "1"

# Shipping code = what a user installs. Dev-only trees are excluded from the static rules.
DEV_DIRS = {"tests", "tools", "contract", ".git", ".venv", "node_modules", "docs", "evidence", ".worktrees",
            "desktop/test", "desktop/src", "desktop/node_modules", "__pycache__", ".pytest_cache", ".metrics",
            "conftest.py"}


def is_live(path: Path) -> bool:
    """True for Adam's live Hermes home or anything in it, except its scratch/cache area (where TMPDIR may live)."""
    p, live = path.resolve(), LIVE_HOME.resolve()
    if p == live:
        return True
    try:
        rel = p.relative_to(live)
    except ValueError:
        return False
    return rel.parts[0] != "cache"


def shipping_files(suffixes: tuple[str, ...]) -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in suffixes:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in DEV_DIRS):
            continue
        out.append(p)
    return sorted(out)


def need_core() -> None:
    ok = (CORE / "hermes_cli" / "main.py").is_file() and CORE_PYTHON.is_file()
    if ok:
        return
    msg = f"Hermes core not available (CF_HERMES_CORE={CORE}, CF_HERMES_PYTHON={CORE_PYTHON})"
    if STRICT:
        pytest.fail(msg)
    pytest.skip(msg)


def run_hermes(args: list[str], home: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    """`hermes <args>` from the pinned v0.22.7 source with an isolated home and a scrubbed environment."""
    need_core()
    assert not is_live(home), "a test must never use the live ~/.hermes"
    env = {"HOME": str(home.parent), "PATH": "/usr/bin:/bin", "HERMES_HOME": str(home), "TMPDIR": "/tmp",
           "PYTHONPATH": str(CORE), "HERMES_DISABLE_LAZY_INSTALLS": "1", "NO_COLOR": "1", "COLUMNS": "200"}
    return subprocess.run([str(CORE_PYTHON), "-m", "hermes_cli.main", *args], env=env, cwd=str(home.parent),
                          capture_output=True, text=True, timeout=timeout)


def load_file_module(name: str, path: Path):
    """Import a single file the way Hermes imports dashboard/plugin_api.py (spec_from_file_location)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plugin_package():
    """The plugin bound as `cuttlefish_theme` (the repo root IS the package, as Hermes loads it)."""
    if "cuttlefish_theme" in sys.modules:
        return sys.modules["cuttlefish_theme"]
    spec = importlib.util.spec_from_file_location("cuttlefish_theme", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cuttlefish_theme"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeCtx:
    """Records what register(ctx) registers. Mirrors the PluginContext methods the plugin may call."""

    def __init__(self, settings: dict | None = None):
        self.hooks: dict[str, list] = {}
        self.cli: dict[str, tuple] = {}
        self.commands: dict[str, object] = {}
        self.tools: list = []
        self._settings = settings or {}

    def register_hook(self, name, callback, **_kw):
        self.hooks.setdefault(name, []).append(callback)

    def register_cli_command(self, name, help, setup_fn, handler_fn, **_kw):  # noqa: A002 - core's signature
        self.cli[name] = (help, setup_fn, handler_fn)

    def register_command(self, name, handler, description="", args_hint="", **_kw):
        self.commands[name] = handler

    def register_tool(self, *a, **kw):
        self.tools.append((a, kw))

    def get_config(self, *_a, **_kw):
        return dict(self._settings)
