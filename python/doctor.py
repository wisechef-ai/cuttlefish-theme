"""``hermes cuttlefish doctor [--json]``: the executable truth table (PLAN §1.5 step 5).

Rows carry ``status`` OK | WARN | FAIL | UNKNOWN | UNAVAILABLE | AVAILABLE, a ``detail``, and a ``how_to_fix`` on every
non-OK row. ``ok`` = no FAIL row. ``state_parity_ok`` = every bus entry's stored state equals the replay of its journal
(CONTRACT §5). Exit 0 iff both. Read-only: doctor never writes."""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import bus, hermes_api, paths, prefs, surfaces
from .domain import reducer, resolve

SCHEMA = "cf2909.doctor/2"
JOURNAL_MAX = bus.JOURNAL_MAX
_RESET_KINDS = ("on_session_reset", "pre_llm_call")
HEARTBEAT_FRESH_S = 20.0


def row(rid, status, detail, fix=None, **extra):
    r = {"id": rid, "status": status, "detail": detail}
    if status not in ("OK", "AVAILABLE"):
        r["how_to_fix"] = fix or ""
    r.update(extra)
    return r


def replay_state(entry):
    """(state, problem). The journal replayed through the §2 reducer, resolved at the last event's time."""
    journal = entry.get("journal")
    if not isinstance(journal, list) or not journal:
        return None, "no journal"
    if len(journal) >= JOURNAL_MAX and not any(j.get("kind") in _RESET_KINDS for j in journal):
        return None, "journal overflowed without a reset event: cannot replay"
    try:
        model = reducer.initial()
        for j in journal:
            model = reducer.reduce(model, j)
        return resolve.resolve(model, journal[-1]["t"]), None
    except Exception as e:  # noqa: BLE001
        return None, "replay failed: %r" % (e,)


def tool_signal(surface_id):
    """D2-CORE-STATE's capability flag per surface (``reducer.TOOL_SIGNAL``); unknown until that lands."""
    flags = getattr(reducer, "TOOL_SIGNAL", None)
    if isinstance(flags, dict) and isinstance(flags.get(surface_id), bool):
        return flags[surface_id]
    return "unknown"


def _plugin_sha(pkg):
    try:
        r = subprocess.run(["git", "-C", str(pkg), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


class Doctor:
    def __init__(self, home, *, env=None, now=None, host=None, pid_alive=None, core=None, pkg_root=surfaces.PKG_ROOT,
                 loader=None):
        self.home = Path(home)
        self.env = os.environ if env is None else env
        self.now = time.time() if now is None else now
        self.host = host or socket.gethostname()
        self.pid_alive = pid_alive or bus.pid_alive
        self.core = core or hermes_api.Core(self.home)
        self.pkg = Path(pkg_root)
        self.loader = loader or hermes_api.cli_widgets_loader

    # -- surfaces --------------------------------------------------------------------------------
    def _surface(self, s):
        sig = tool_signal(s.id)
        base = {"surface": s.id, "kind": "surface", "tool_signal": sig}
        rid = "surface." + s.id
        if not surfaces.shipped(s, self.pkg):
            return row(rid, "UNAVAILABLE", "not in this build (%s is missing)" % s.artifact,
                       "update the plugin to a build that ships %s" % s.artifact, **base)
        if s.id == "classic-cli":
            ok, why = self.loader()
            if not ok:
                return row(rid, "UNAVAILABLE", why,
                           "use the TUI or desktop, or carry the D2-CLI-CORE patch (adamkrawczyk/hermes-agent "
                           "feat/cli-widgets); then run: hermes cuttlefish setup", **base)
        d = surfaces.dest(self.home, s)
        if s.id == "desktop":
            mat = surfaces.materialized_by_core(self.home)
            if mat is not None:
                return self._desktop_marker(rid, mat, base)
        if not d.is_symlink():
            what = "exists but is not our link" if d.exists() else "not installed"
            return row(rid, "UNAVAILABLE", "%s: %s" % (d, what), "run: hermes cuttlefish setup", **base)
        if not d.exists():
            return row(rid, "UNAVAILABLE", "%s is a dangling link (the package moved)" % d,
                       "run: hermes cuttlefish uninstall --keep-plugin && hermes cuttlefish setup", **base)
        extra = ""
        if s.id == "tui":
            extra = self._heartbeat_note()
        if s.id == "desktop":
            extra = "; enabled in the app: unknown (a renderer decision). Check Settings -> Plugins -> Cuttlefish -> Desktop"
        return row(rid, "AVAILABLE", "linked %s%s" % (d, extra), **base)

    def _desktop_marker(self, rid, mat, base):
        marker = bus.read_json(mat / ".hermes-package.json") or {}
        src = self.pkg / "desktop" / "plugin.js"
        try:
            src_ms = src.stat().st_mtime * 1000
        except OSError:
            src_ms = None
        seen = marker.get("sourceMtimeMs")
        if src_ms is not None and isinstance(seen, (int, float)) and seen + 1 < src_ms:
            return row(rid, "UNAVAILABLE", "materialized copy %s is older than the package's desktop/plugin.js" % mat,
                       "in the app: Plugins -> Rescan, or run: hermes cuttlefish setup (pokes the reconcile)", **base)
        return row(rid, "AVAILABLE", "materialized by core at %s; enabled in the app: unknown (a renderer decision). "
                   "Check Settings -> Plugins -> Cuttlefish -> Desktop" % mat, **base)

    def _heartbeat_note(self):
        hb = bus.read_json(paths.widget_heartbeat_file(self.home))
        t = None
        if isinstance(hb, dict):
            for k in ("t", "ts", "heartbeat"):
                if isinstance(hb.get(k), (int, float)) and not isinstance(hb.get(k), bool):
                    t = hb[k]
                    break
        if t is None:
            return "; widget load unconfirmed (no widget-heartbeat.json yet)"
        age = self.now - t
        return "; widget loaded (heartbeat %ds ago)" % age if age <= HEARTBEAT_FRESH_S else \
            "; widget heartbeat is stale (%ds): restart `hermes --tui`" % age

    # -- other rows --------------------------------------------------------------------------------
    def _plugin_row(self):
        try:
            cfg = self.core.read_config()
        except hermes_api.CoreUnavailable as e:
            return row("plugin.enabled", "UNKNOWN", str(e), "run doctor as `hermes cuttlefish doctor`")
        if hermes_api.plugin_enabled(cfg):
            return row("plugin.enabled", "OK", "cuttlefish-theme is in plugins.enabled")
        return row("plugin.enabled", "WARN", "cuttlefish-theme is not enabled for this home",
                   "run: hermes plugins enable cuttlefish-theme")

    def _hooks_row(self):
        st = bus.read_json(paths.hooks_file(self.home))
        if not isinstance(st, dict):
            return row("hooks", "UNKNOWN", "no hooks.json yet: the plugin has not loaded in this home",
                       "start a session after enabling the plugin")
        un = st.get("unavailable") or []
        if un:
            return row("hooks", "WARN", "core lacks hooks: %s (those events are never seen)" % ", ".join(un),
                       "update Hermes core; the surfaces degrade, they do not fail")
        return row("hooks", "OK", "%d hooks registered" % len(st.get("registered") or []))

    def _api_row(self):
        p = self.pkg / "dashboard" / "plugin_api.py"
        try:
            spec = importlib.util.spec_from_file_location("_cf_doctor_plugin_api", p)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
                n = len(mod.state()["sessions"])
                mod.identity()
            finally:
                sys.modules.pop(spec.name, None)
        except Exception as e:  # noqa: BLE001
            return row("api", "FAIL", "dashboard/plugin_api.py: %s: %s" % (type(e).__name__, e),
                       "reinstall the plugin: hermes plugins update cuttlefish-theme")
        return row("api", "OK", "GET /identity and /state answer in-process (%d session(s)); no dashboard probed" % n)

    def _binding_row(self):
        f = self.env.get("HERMES_TUI_ACTIVE_SESSION_FILE")
        if not f:
            return row("binding", "UNKNOWN", "HERMES_TUI_ACTIVE_SESSION_FILE is unset (not inside a TUI session)",
                       "run doctor from a terminal opened by `hermes --tui`")
        try:
            age = self.now - os.stat(f).st_mtime
        except OSError:
            return row("binding", "WARN", "%s does not exist" % f, "restart `hermes --tui`")
        return row("binding", "OK" if age < 3600 else "WARN", "session binding file is %ds old" % age,
                   "restart `hermes --tui`")

    def _bus(self):
        entries = bus.read_entries(self.home)
        rows, parity_ok, live, newest = [], True, 0, None
        stale, bad = [], []
        for root, e in sorted(entries.items()):
            state = resolve.resolve_entry(e, now=self.now, this_host=self.host, pid_alive=self.pid_alive)
            if state != "unknown":
                live += 1
            hb = e.get("heartbeat")
            if isinstance(hb, (int, float)) and not isinstance(hb, bool):
                newest = hb if newest is None else max(newest, hb)
                pid = e.get("owner_pid")
                alive = e.get("owner_host") == self.host and isinstance(pid, int) and self.pid_alive(pid)
                if alive and self.now - hb > resolve.STALE_S:
                    stale.append("%s (pid %s, heartbeat %ds old)" % (root, pid, self.now - hb))
            replay, problem = replay_state(e)
            if problem or replay != e.get("state"):
                bad.append("%s: %s" % (root, problem or "stored %r != replay %r" % (e.get("state"), replay)))
        if stale:
            rows.append(row("bus.fresh", "FAIL", "owner alive but heartbeat stale: " + "; ".join(stale),
                            "the writer is wedged: restart that Hermes session"))
        else:
            rows.append(row("bus.fresh", "OK", "%d bus entr%s, none wedged" % (len(entries), "y" if len(entries) == 1 else "ies")))
        if bad:
            parity_ok = False
            rows.append(row("bus.parity", "FAIL", "; ".join(bad), "file a bug with the bus file attached"))
        else:
            rows.append(row("bus.parity", "OK", "stored state == journal replay for every entry"))
        rows.append(row("peers", "OK" if live else "UNKNOWN", "%d live session(s)" % live,
                        "start a session with the plugin enabled"))
        if newest is None:
            rows.append(row("last_event", "UNKNOWN", "no bus entries yet", "start a session with the plugin enabled"))
        else:
            rows.append(row("last_event", "OK", "newest heartbeat %ds ago" % (self.now - newest)))
        return rows, parity_ok

    def _color_row(self):
        e = self.env
        if e.get("COLORTERM", "").lower() in ("truecolor", "24bit") or e.get("LC_TERMINAL") == "iTerm2":
            return row("truecolor", "OK", "truecolor terminal")
        ssh = bool(e.get("SSH_CONNECTION") or e.get("SSH_TTY"))
        return row("truecolor", "WARN", "no COLORTERM=truecolor%s: dots fall back to the 256-colour cube" %
                   (" (over SSH)" if ssh else ""), "export COLORTERM=truecolor (SSH: set SendEnv/AcceptEnv)")

    def _twinkle_row(self):
        p = prefs.load(self.home)
        on, why = prefs.twinkle_effective(p["twinkle"], self.env)
        return row("twinkle", "OK", "twinkle=%s -> idle twinkle %s (%s)" % (p["twinkle"], "ON" if on else "OFF", why))

    # -- assemble -----------------------------------------------------------------------------------
    def report(self):
        bus_rows, parity_ok = self._bus()
        rows = [self._plugin_row(), self._hooks_row(), self._api_row()]
        rows += [self._surface(s) for s in surfaces.SURFACES]
        rows += [self._binding_row()] + bus_rows + [self._color_row(), self._twinkle_row()]
        return {"schema": SCHEMA, "ok": not any(r["status"] == "FAIL" for r in rows), "state_parity_ok": parity_ok,
                "rows": rows, "home": str(self.home), "plugin_sha": _plugin_sha(self.pkg)}


def render(report, out=print):
    out("cuttlefish doctor  (HERMES_HOME=%s)" % report["home"])
    for r in report["rows"]:
        line = "  [%-11s] %-16s %s" % (r["status"], r["id"], r["detail"])
        if r["id"].startswith("surface."):
            line += "  (tool signal: %s)" % json.dumps(r["tool_signal"])
        out(line)
        if r.get("how_to_fix"):
            out("  %-14s fix: %s" % ("", r["how_to_fix"]))
    out("ok=%s state_parity_ok=%s" % (str(report["ok"]).lower(), str(report["state_parity_ok"]).lower()))


def run(home, *, as_json=False, out=print, **kw):
    rep = Doctor(home, **kw).report()
    if as_json:
        out(json.dumps(rep, indent=2))
    else:
        render(rep, out)
    return 0 if rep["ok"] and rep["state_parity_ok"] else 1
