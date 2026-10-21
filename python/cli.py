"""``hermes cuttlefish setup | doctor | legend | demo | set | uninstall``.

Adapters only: colours come from tokens.json, states from the domain reducer, files from the P3 stores. Exit codes:
0 ok, 1 a check failed (doctor) or a step failed (uninstall), 2 a bad argument (set), 130 interrupted (demo)."""
import argparse
import sys

from . import demo as demo_mod
from . import doctor as doctor_mod
from . import legend as legend_mod
from . import paths, prefs, setup_cmd


def setup_parser(parser):
    sub = parser.add_subparsers(dest="cuttle_cmd")
    s = sub.add_parser("setup", help="Install the skin and surface widgets (idempotent, recorded in a ledger)")
    s.add_argument("--switch-skin", action="store_true", help="Also set display.skin to cuttlefish (never implied off a TTY)")
    s.add_argument("--enable", action="store_true", help="Also enable the plugin in this home's config")
    d = sub.add_parser("doctor", help="Check every surface and the state bus")
    d.add_argument("--json", action="store_true", help="Machine-readable report (schema cf2909.doctor/2)")
    sub.add_parser("legend", help="What each state looks like and what to do")
    dm = sub.add_parser("demo", help="Walk every state on a reserved demo session")
    dm.add_argument("--seconds", type=float, default=0.0, help="Total run time (default 20)")
    st = sub.add_parser("set", help="Change a preference: mantle off|on|1|2, twinkle auto|on|off, cells auto|half|bg")
    st.add_argument("key", nargs="?", help="mantle | twinkle | cells (omit to show the current values)")
    st.add_argument("value", nargs="?")
    u = sub.add_parser("uninstall", help="Undo exactly what setup recorded, then remove the plugin")
    u.add_argument("--keep-plugin", action="store_true", help="Do not run `hermes plugins remove`")


def _set(home, key, value, out, err):
    if key is None:
        for k in prefs.KEYS:
            out("%-8s %s" % (k, prefs.load(home)[k]))
        return 0
    if value is None:
        err("usage: hermes cuttlefish set %s <%s>" % (key, "|".join(prefs.CHOICES.get(key, ("value",)))))
        return 2
    try:
        p = prefs.set_pref(home, key, value)
    except ValueError as e:
        err("hermes cuttlefish set: %s" % e)
        return 2
    out("%s = %s" % (key, p[key]))
    if key == "twinkle":
        on, why = prefs.twinkle_effective(p[key])
        out("  idle twinkle is %s in this shell: %s" % ("ON" if on else "OFF", why))
    return 0


def run(args, home=None, out=print, err=None):
    err = err or (lambda m: print(m, file=sys.stderr))
    home = home or paths.hermes_home()
    cmd = getattr(args, "cuttle_cmd", None)
    if cmd == "setup":
        return setup_cmd.Setup(home, out=out).run(switch_skin=True if args.switch_skin else None, enable=args.enable)
    if cmd == "doctor":
        return doctor_mod.run(home, as_json=args.json, out=out)
    if cmd == "legend":
        return legend_mod.run(out=out)
    if cmd == "demo":
        return demo_mod.run(home, seconds=args.seconds, out=out)
    if cmd == "set":
        return _set(home, args.key, args.value, out, err)
    if cmd == "uninstall":
        return setup_cmd.Uninstall(home, out=out).run(keep_plugin=args.keep_plugin)
    err("usage: hermes cuttlefish {setup|doctor|legend|demo|set|uninstall}   (try: hermes cuttlefish doctor)")
    return 2


def handler(args):
    return run(args)


def main(argv=None, home=None):
    p = argparse.ArgumentParser(prog="hermes cuttlefish")
    setup_parser(p)
    return run(p.parse_args(argv), home=home)


def register(ctx):
    ctx.register_cli_command("cuttlefish", help="Session identity dots: setup, doctor, legend, demo, set, uninstall",
                             setup_fn=setup_parser, handler_fn=handler,
                             description="Sparse identity dots that follow the agent's state. No background is ever painted.")
