"""``hermes cuttlefish <doctor|skin|legend>`` — the plugin's own CLI.

SPEC C5: config file only, no UI; this is where a user points at the config,
installs the classic-CLI skin, and reads the vocabulary. The handlers print and
return an exit code (the argparse ``func`` convention core wires up).
"""

from __future__ import annotations

import argparse

from . import liveconfig, skin
from .settings import DEFAULT_SETTINGS, MOTIONS, PATTERN_KINDS, SIGNALS

ACTIONS = ("doctor", "skin", "legend")


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """Wire the ``hermes cuttlefish`` subparser (core hands us the parser)."""
    parser.add_argument("action", nargs="?", choices=ACTIONS, default="doctor",
                        help="doctor: config + skin state · skin: install the classic-CLI skin · legend: the vocabulary")
    parser.add_argument("--remove", action="store_true",
                        help="with 'skin': uninstall instead of install")


def run(args: argparse.Namespace) -> int:
    """Dispatch one action; every handler is a plain ``func(args) -> rc``."""
    action = getattr(args, "action", None) or "doctor"
    return {"doctor": doctor, "skin": apply_skin, "legend": legend}[action](args)


def doctor(_args: argparse.Namespace) -> int:
    """Report version, config location, the resolved settings, the skin state."""
    home = liveconfig.hermes_home()
    resolved, warnings = liveconfig.resolve_live(home)
    print(f"cuttlefish-theme {liveconfig.plugin_version()}")
    print(f"config: {liveconfig.config_path(home)}")
    states = resolved["states"]
    print(f"settings: intensity {resolved['intensity']} · motion {resolved['motion']} · "
          f"{len(states)} states · {len(resolved['patterns'])} patterns")
    if warnings:
        for warning in warnings:
            print(f"  warning [{warning['code']}] {warning['path']}: {warning['message']}")
    else:
        print("  warnings: none")
    installed = skin.skin_target(home)
    print(f"skin: {'installed at ' + str(installed) if installed.is_file() else 'not installed (hermes cuttlefish skin)'}")
    return 0


def apply_skin(args: argparse.Namespace) -> int:
    """Install (default) or remove (``--remove``) the static classic-CLI skin."""
    home = liveconfig.hermes_home()
    if getattr(args, "remove", False):
        if skin.uninstall(home):
            print(f"removed {skin.skin_target(home)}")
        else:
            print(f"kept {skin.skin_target(home)} (not ours anymore or absent)")
        return 0
    target = skin.install(home)
    print(f"installed {target}")
    print("select it with: hermes config set display.skin cuttlefish")
    return 0


def legend(_args: argparse.Namespace) -> int:
    """Teach the language: the states, the pattern kinds, where config lives."""
    print("hue is the session's identity; state is pattern + brightness (never a hue change)")
    print(f"motion: {' | '.join(MOTIONS)} · signals: {' '.join(SIGNALS)}")
    print("config: plugins.entries.cuttlefish-theme.settings.{intensity,motion,states,patterns}")
    resolved, _ = liveconfig.resolve_live()
    states = resolved["states"]
    order = [name for name in DEFAULT_SETTINGS["states"] if name in states] + \
            [name for name in states if name not in DEFAULT_SETTINGS["states"]]
    for name in order:
        state = states[name]
        label = f" \"{state['label']}\"" if state["label"] else ""
        print(f"  {name:<16} {state['when']:<12} {state['pattern']:<8} priority {state['priority']:>4}{label}")
    print(f"pattern kinds: {' '.join(PATTERN_KINDS)}")
    return 0
