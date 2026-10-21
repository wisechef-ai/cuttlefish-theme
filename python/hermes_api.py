"""The ONLY module that touches the running core (``hermes_cli``): config read/write, plugin removal,
the desktop reconcile poke, and the classic-CLI loader feature-detect. Everything else takes a ``Core``
so tests can hand in a fake and the real one is exercised by a subprocess run against a temp HERMES_HOME.

Never imported at module load by anything but the CLI: the agent-side hooks must not depend on it."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_NAMES = ("cuttlefish-theme", "cuttlefish_theme")
REMOVE_NAME = "cuttlefish-theme"


class CoreUnavailable(Exception):
    """hermes_cli cannot be imported in this interpreter (the CLI is not running inside Hermes)."""


class Core:
    """Thin adapter over ``hermes_cli.config`` (comment-preserving round-trip writes)."""

    def __init__(self, home):
        self.home = Path(home)

    def _cfg(self):
        try:
            from hermes_cli import config as cfg
        except Exception as e:  # noqa: BLE001
            raise CoreUnavailable("cannot import hermes_cli (%s: %s)" % (type(e).__name__, e)) from e
        return cfg

    @property
    def config_path(self):
        return self.home / "config.yaml"

    def read_config(self):
        """The user's config exactly as written (no defaults merged)."""
        return self._cfg().read_user_config_raw(self.config_path)

    def write_config(self, data):
        """Persist the complete desired state; omitted keys are deliberately deleted."""
        self._cfg().atomic_config_replace(self.config_path, data)

    def remove_plugin(self):
        """``hermes plugins remove cuttlefish-theme`` through THIS interpreter (never the PATH hermes)."""
        env = dict(os.environ, HERMES_HOME=str(self.home))
        r = subprocess.run([sys.executable, "-m", "hermes_cli.main", "plugins", "remove", REMOVE_NAME],
                           capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, (r.stdout + r.stderr).strip()


def plugin_enabled(cfg):
    plugins = cfg.get("plugins") if isinstance(cfg, dict) else None
    enabled = plugins.get("enabled") if isinstance(plugins, dict) else None
    return isinstance(enabled, list) and any(n in enabled for n in PLUGIN_NAMES)


def skin_of(cfg):
    display = cfg.get("display") if isinstance(cfg, dict) else None
    return display.get("skin") if isinstance(display, dict) else None


def desktop_poke(home):
    """Spike 10: a running app does not watch ``plugins/``; one entry change (mkdir+rmdir) in
    ``desktop-plugins/`` makes it reconcile within ~1 s. Residue-free. Returns True if poked."""
    d = Path(home) / "desktop-plugins"
    if not d.is_dir():
        return False
    p = d / (".cuttlefish-poke-%d" % os.getpid())
    try:
        p.mkdir()
        p.rmdir()
    except OSError:
        return False
    return True


def cli_widgets_loader(core_dir=None):
    """(available, reason). The classic CLI has no plugin loader (core PLG-7); D2-CLI-CORE adds a generic
    ``$HERMES_HOME/cli-widgets/*.py`` loader. Detected by its presence in the CLI mixins of the core that is
    importable here, not by version: a fork that carries the patch is AVAILABLE, stock upstream is not."""
    if core_dir is None:
        try:
            spec = importlib.util.find_spec("hermes_cli")
        except (ImportError, ValueError):
            spec = None
        if spec is None or not spec.submodule_search_locations:
            return False, "hermes_cli is not importable here, so the classic-CLI loader cannot be detected"
        core_dir = list(spec.submodule_search_locations)[0]
    core_dir = Path(core_dir)
    for name in ("cli_tui_mixin.py", "cli_init_mixin.py"):
        try:
            text = (core_dir / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "cli-widgets" in text or "cli_widgets" in text:
            return True, "core loads $HERMES_HOME/cli-widgets/*.py (%s)" % name
    return False, ("this core has no cli-widgets loader (classic CLI never loads plugins, PLG-7); "
                   "it needs the D2-CLI-CORE fork patch")

