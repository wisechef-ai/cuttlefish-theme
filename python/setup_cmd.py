"""``hermes cuttlefish setup`` / ``uninstall``. Every change is written to the ledger BEFORE it is made, and
``uninstall`` undoes only what the ledger says, in reverse, re-verifying each item first (CONTRACT §4)."""
import hashlib
import os
import shutil
import sys
from pathlib import Path

from . import hermes_api, ledger, paths, surfaces

SKIN_NAME = "cuttlefish"
PLUGIN = hermes_api.REMOVE_NAME


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_default_skin(name):
    return name in (None, "", "default")


class Setup:
    def __init__(self, home, *, pkg_root=surfaces.PKG_ROOT, core=None, out=print, ask=None, tty=None,
                 loader=None, poke=None):
        self.home = Path(home)
        self.pkg = Path(pkg_root)
        self.core = core or hermes_api.Core(self.home)
        self.out = out
        self.tty = sys.stdin.isatty() if tty is None else tty
        self.ask = ask or (lambda q: input(q))
        self.loader = loader or hermes_api.cli_widgets_loader
        self.poke = poke or hermes_api.desktop_poke
        self.changes = 0
        self.notes = []

    # -- helpers -------------------------------------------------------------------------------
    def _say(self, tag, msg):
        self.out("  %-12s %s" % (tag, msg))

    def _mkdirs(self, d):
        """Create ``d`` (and missing parents below HOME), recording each directory we create first."""
        missing = []
        cur = Path(d)
        while not cur.exists() and cur != cur.parent:
            missing.append(cur)
            cur = cur.parent
        for p in reversed(missing):
            ledger.record(self.home, {"op": "mkdir", "path": str(p)})
            p.mkdir()
            self.changes += 1

    def _confirm(self, question):
        if not self.tty:
            return False
        try:
            return self.ask(question + " [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    # -- steps ---------------------------------------------------------------------------------
    def skin(self):
        src = self.pkg / "skins" / "cuttlefish.yaml"
        dst = self.home / "skins" / "cuttlefish.yaml"
        if not src.is_file():
            return self._say("skin", "not in this build (skins/cuttlefish.yaml missing)")
        if dst.exists() or dst.is_symlink():
            if dst.is_file() and _sha(dst) == _sha(src):
                return self._say("skin", "already installed: %s" % dst)
            return self._say("skin", "%s exists and is not ours: left untouched (it is yours)" % dst)
        self._mkdirs(dst.parent)
        ledger.record(self.home, {"op": "copy", "path": str(dst), "sha256": _sha(src)})
        tmp = dst.with_name(".tmp-" + dst.name)
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        self.changes += 1
        self._say("skin", "installed %s (no background key: your terminal keeps its own)" % dst)

    def _link(self, surface, source):
        dst = surfaces.dest(self.home, surface)
        if dst.is_symlink() and os.readlink(dst) == str(source):
            return self._say(surface.id, "already linked: %s" % dst)
        if dst.exists() or dst.is_symlink():
            return self._say(surface.id, "%s exists and is not ours: left untouched (it is yours)" % dst)
        self._mkdirs(dst.parent)
        ledger.record(self.home, {"op": "symlink", "path": str(dst), "target": str(source)})
        os.symlink(source, dst)
        self.changes += 1
        self._say(surface.id, "linked %s -> %s" % (dst, source))

    def surfaces(self):
        for s in surfaces.SURFACES:
            if not surfaces.shipped(s, self.pkg):
                self._say(s.id, "not in this build (%s)" % s.artifact)
                continue
            if s.id == "classic-cli":
                ok, why = self.loader()
                if not ok:
                    self._say(s.id, "UNAVAILABLE: %s; not linked" % why)
                    continue
            if s.id == "desktop":
                mat = surfaces.materialized_by_core(self.home)
                if mat is not None:
                    self._say(s.id, "already materialized by core at %s; not linking" % mat)
                    continue
            self._link(s, self.pkg / s.link_src)

    def _config(self):
        try:
            return self.core.read_config()
        except hermes_api.CoreUnavailable as e:
            self._say("config", "skipped: %s" % e)
            return None

    def switch_skin(self, switch):
        cfg = self._config()
        if cfg is None:
            return
        cur = hermes_api.skin_of(cfg)
        if cur == SKIN_NAME:
            return self._say("display.skin", "already %s" % SKIN_NAME)
        if not (self.home / "skins" / "cuttlefish.yaml").is_file():
            return self._say("display.skin", "not switched: the cuttlefish skin is not installed")
        if not _is_default_skin(cur):
            self._say("display.skin", "you use the skin %r; default answer is N" % cur)
        if not switch and not (switch is None and self._confirm("Switch display.skin to %r?" % SKIN_NAME)):
            return self._say("display.skin", "not switched (use --switch-skin, or: hermes config set display.skin %s)"
                             % SKIN_NAME)
        display = cfg.get("display")
        entry = {"op": "config", "key": "display.skin", "value": SKIN_NAME,
                 "prior_present": isinstance(display, dict) and "skin" in display,
                 "prior_value": cur, "display_created": not isinstance(display, dict),
                 "config_created": not self.core.config_path.exists()}
        ledger.record(self.home, entry)
        new = dict(cfg)
        new["display"] = dict(display) if isinstance(display, dict) else {}
        new["display"]["skin"] = SKIN_NAME
        self.core.write_config(new)
        self.changes += 1
        self._say("display.skin", "switched %r -> %r (recorded; uninstall restores it)" % (cur, SKIN_NAME))

    def enable_plugin(self, enable):
        cfg = self._config()
        if cfg is None:
            return
        if hermes_api.plugin_enabled(cfg):
            return self._say("plugin", "enabled")
        if not enable and not self._confirm("Enable the %s plugin?" % PLUGIN):
            return self._say("plugin", "NOT enabled. Run: hermes plugins enable %s   (or re-run setup with --enable)"
                             % PLUGIN)
        plugins = cfg.get("plugins")
        enabled = plugins.get("enabled") if isinstance(plugins, dict) else None
        disabled = plugins.get("disabled") if isinstance(plugins, dict) else None
        ledger.record(self.home, {
            "op": "plugin_enable", "name": PLUGIN, "plugins_created": not isinstance(plugins, dict),
            "enabled_created": not isinstance(enabled, list),
            "was_disabled": isinstance(disabled, list) and PLUGIN in disabled,
            "config_created": not self.core.config_path.exists()})
        new = dict(cfg)
        new["plugins"] = dict(plugins) if isinstance(plugins, dict) else {}
        new["plugins"]["enabled"] = list(enabled or []) + [PLUGIN]
        if isinstance(disabled, list) and PLUGIN in disabled:
            new["plugins"]["disabled"] = [n for n in disabled if n != PLUGIN]
        self.core.write_config(new)
        self.changes += 1
        self._say("plugin", "enabled %s (recorded)" % PLUGIN)

    def run(self, *, switch_skin=None, enable=False):
        self.out("cuttlefish setup  (HERMES_HOME=%s)" % self.home)
        self.skin()
        self.surfaces()
        self.switch_skin(switch_skin)
        self.enable_plugin(enable)
        if self.changes and self.poke(self.home):
            self._say("desktop", "reconcile poked (a running app picks the half up within ~1 s)")
        if not self.changes:
            self.out("already set up: 0 changes")
        else:
            self.out("%d change(s) recorded in %s" % (self.changes, paths.ledger_file(self.home)))
        self.out("")
        self.out("What you will see, and where:")
        self.out("  TUI           a 1-2 row dot strip above the prompt (restart `hermes --tui`)")
        self.out("  Desktop       the field pane. Second consent: Settings -> Plugins -> Cuttlefish -> Desktop switch")
        self.out("  Classic CLI   a strip above the prompt, only on a core with the cli-widgets loader")
        self.out("  Check any time: hermes cuttlefish doctor")
        return 0


# -- uninstall ---------------------------------------------------------------------------------
class Uninstall:
    def __init__(self, home, *, core=None, out=print, poke=None):
        self.home = Path(home)
        self.core = core or hermes_api.Core(self.home)
        self.out = out
        self.poke = poke or hermes_api.desktop_poke

    def _say(self, tag, msg):
        self.out("  %-12s %s" % (tag, msg))

    def _undo_config(self, e):
        try:
            cfg = self.core.read_config()
        except hermes_api.CoreUnavailable as ex:
            return self._say("display.skin", "left: %s" % ex)
        display = cfg.get("display") if isinstance(cfg.get("display"), dict) else {}
        if display.get("skin") != e["value"]:
            return self._say("display.skin", "left as %r: you changed it since setup" % display.get("skin"))
        new = dict(cfg)
        new["display"] = dict(display)
        if e["prior_present"]:
            new["display"]["skin"] = e["prior_value"]
        else:
            del new["display"]["skin"]
            if not new["display"] and e["display_created"]:
                del new["display"]
        self._write_or_remove(new, e.get("config_created"))
        self._say("display.skin", "restored to %r" % (e["prior_value"] if e["prior_present"] else "(unset)"))

    def _undo_plugin_enable(self, e):
        try:
            cfg = self.core.read_config()
        except hermes_api.CoreUnavailable as ex:
            return self._say("plugin", "left: %s" % ex)
        plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
        enabled = plugins.get("enabled")
        if not isinstance(enabled, list) or e["name"] not in enabled:
            return self._say("plugin", "left: no longer in plugins.enabled")
        new = dict(cfg)
        new["plugins"] = dict(plugins)
        rest = [n for n in enabled if n != e["name"]]
        if rest or not e["enabled_created"]:
            new["plugins"]["enabled"] = rest
        else:
            del new["plugins"]["enabled"]
        if e["was_disabled"]:
            new["plugins"]["disabled"] = list(plugins.get("disabled") or []) + [e["name"]]
        if not new["plugins"] and e["plugins_created"]:
            del new["plugins"]
        self._write_or_remove(new, e.get("config_created"))
        self._say("plugin", "enable undone")

    def _write_or_remove(self, new, config_created):
        if config_created and not new:
            self.core.config_path.unlink(missing_ok=True)  # we created it, and nothing else is in it
        else:
            self.core.write_config(new)

    def _remove_owned_state(self):
        """Remove only the state files Cuttlefish itself writes; anything else in the shared
        data directory is the user's and stays. Directories go only if they end up empty."""
        cf = paths.cuttlefish_dir(self.home)
        bd = paths.bus_dir(self.home)
        owned = [paths.identity_file(self.home), paths.identity_lock(self.home),
                 paths.hooks_file(self.home), paths.prefs_file(self.home),
                 paths.widget_heartbeat_file(self.home), paths.ledger_file(self.home)]
        for d in (bd, cf):  # our atomic-write leftovers
            if d.is_dir():
                owned += [p for p in d.iterdir() if p.name.startswith(".tmp-") and p.is_file()]
        if bd.is_dir():  # <lineage>.json bus entries
            owned += [p for p in bd.iterdir() if p.suffix == ".json" and p.is_file() and not p.is_symlink()]
        removed = 0
        for p in owned:
            try:
                p.unlink()
                removed += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                self._say("state", "left %s: %s" % (p, exc))
        if removed:
            self._say("state", "removed %d Cuttlefish state file(s) under %s" % (removed, cf))
        for d in (bd, cf):
            try:
                d.rmdir()
                self._say("dir", "removed %s" % d)
            except OSError:
                if d.exists():
                    self._say("dir", "left %s: holds files that are not ours" % d)

    def run(self, *, keep_plugin=False):
        self.out("cuttlefish uninstall  (HERMES_HOME=%s)" % self.home)
        doc = ledger.load(self.home)
        if not doc["entries"]:
            self._say("ledger", "nothing recorded: no setup change to restore")
        for e in reversed(doc["entries"]):
            op = e.get("op")
            if op == "config":
                self._undo_config(e)
            elif op == "plugin_enable":
                self._undo_plugin_enable(e)
            elif op == "symlink":
                p = Path(e["path"])
                if p.is_symlink() and os.readlink(p) == e["target"]:
                    p.unlink()
                    self._say("link", "removed %s" % p)
                else:
                    self._say("link", "left %s: not our link any more" % p)
            elif op == "copy":
                p = Path(e["path"])
                if p.is_file() and _sha(p) == e["sha256"]:
                    p.unlink()
                    self._say("file", "removed %s" % p)
                elif p.exists():
                    self._say("file", "left %s: changed since setup (yours now)" % p)
            elif op == "mkdir":
                p = Path(e["path"])
                try:
                    p.rmdir()
                    self._say("dir", "removed %s" % p)
                except OSError:
                    if p.exists():
                        self._say("dir", "left %s: not empty" % p)
        self._remove_owned_state()
        self.poke(self.home)
        if keep_plugin:
            self._say("plugin", "kept (--keep-plugin)")
        else:
            rc, msg = self.core.remove_plugin()
            self._say("plugin", "hermes plugins remove %s: %s" % (PLUGIN, "ok" if rc == 0 else "FAILED rc=%d %s" % (rc, msg)))
            self.poke(self.home)
            if rc != 0:
                return 1
        return 0
