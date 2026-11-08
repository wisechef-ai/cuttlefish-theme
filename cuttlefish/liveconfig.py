"""Where settings live and how to read them back (SPEC C5: config file only).

Settings sit in ``<hermes home>/config.yaml`` under
``plugins.entries.cuttlefish-theme.settings``. Reading is always LIVE: the
dashboard's ``/config`` route re-reads the file on every request, so an edit
applies without a restart. Core's config module is a public door and resolves
the home exactly like the running process; without Hermes on the path we fall
back to ``HERMES_HOME`` and ``~/.hermes``.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

try:  # the normal case: loaded as part of the cuttlefish package (tests, the CLI)
    from .settings import resolve_settings
except ImportError:  # by-path load (the dashboard's plugin_api.py) has no parent package

    def _load_settings() -> Any:
        spec = importlib.util.spec_from_file_location(
            "cuttlefish_settings_by_path", Path(__file__).with_name("settings.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    resolve_settings = _load_settings().resolve_settings

#: The catalog name: the key our settings live under in config.yaml.
PLUGIN_KEY = "cuttlefish-theme"


_UNREADABLE = {"path": "config", "code": "type",
               "message": "config.yaml is not valid YAML; using the default settings"}


def _load_yaml(path: Path) -> tuple[bool, Any]:
    """``(True, data)`` for YAML we can read, ``(False, None)`` for YAML we cannot. Never raises for a parse problem.

    PyYAML is NOT a guaranteed dependency of a Hermes runtime (Python 3.14 installs lack it), so importing it at module
    level broke the whole plugin. Order: core's public door ``hermes_cli.config.read_user_config_raw`` (the parser core
    reads config with; ``hermes_cli.config`` is on the catalog's public-import list, ``hermes_yaml`` is not), then
    PyYAML only when it is installed (standalone runs, the dev venv). Neither available is unreadable: the caller
    degrades to the defaults with a warning. ``OSError`` propagates: a file we cannot open is an absent config.
    """
    try:
        from hermes_cli.config import read_user_config_raw as reader  # core's public door, lazy: Hermes hosts only
    except ImportError:
        try:
            import yaml  # optional: standalone/dev only, never required at import time
        except ImportError:
            return False, None

        def reader(p: Path) -> Any:
            return yaml.safe_load(p.read_text(encoding="utf-8"))
    try:
        return True, reader(path)
    except OSError:
        raise
    except Exception:  # core raises ruamel's YAMLError, PyYAML its own; both mean "not YAML we can read"
        return False, None


def hermes_home() -> Path:
    """The Hermes home this process serves (core's resolver, else env/default)."""
    try:
        from hermes_cli.config import get_process_hermes_home  # public door, lazy
        home = get_process_hermes_home()
        if home:
            return Path(home)
    except Exception:
        pass
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def config_path(home: Path | None = None) -> Path:
    return (home or hermes_home()) / "config.yaml"


def plugin_version() -> str:
    """The version from plugin.yaml — the one file both halves report. Empty when no YAML reader is available."""
    try:
        ok, data = _load_yaml(Path(__file__).resolve().parents[1] / "plugin.yaml")
    except OSError:
        return ""
    return str(data.get("version", "")) if ok and isinstance(data, dict) else ""


def read_raw_settings(home: Path) -> tuple[Any, list[dict[str, str]]]:
    """The plugin's raw ``settings:`` mapping from ``<home>/config.yaml``.

    Returns ``(None, [])`` when there is nothing to read (no file, no entry):
    that is not a problem, it is an empty config. Broken YAML degrades to the
    defaults with a warning instead of an error."""
    try:
        ok, data = _load_yaml(config_path(home))  # a hostile nesting depth is "not YAML we can read" too
    except OSError:
        return None, []
    if not ok:
        return None, [_UNREADABLE]
    entry = data.get("plugins") if isinstance(data, dict) else None
    entry = entry.get("entries") if isinstance(entry, dict) else None
    entry = entry.get(PLUGIN_KEY) if isinstance(entry, dict) else None
    raw = entry.get("settings") if isinstance(entry, dict) else None
    return raw, []


def resolve_live(home: Path | None = None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Resolved settings + warnings for the home being served, read fresh."""
    home = home or hermes_home()
    raw, load_warnings = read_raw_settings(home)
    settings, warnings = resolve_settings(raw)
    return settings, load_warnings + warnings
