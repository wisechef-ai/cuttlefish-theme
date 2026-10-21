"""``state.json`` (CONTRACT §4): the three user prefs written by ``hermes cuttlefish set``. Atomic writes."""
import os

from . import bus, paths

SCHEMA = "cf2909.prefs/1"
KEYS = ("mantle", "twinkle", "cells")
CHOICES = {"mantle": ("off", "on", "1", "2"), "twinkle": ("auto", "on", "off"), "cells": ("auto", "half", "bg")}
DEFAULTS = {"mantle": "on", "twinkle": "auto", "cells": "auto"}


def normalise(key, raw):
    """The stored value for ``key=raw`` (mantle 1/2 are stored as ints), or ValueError."""
    if key not in CHOICES:
        raise ValueError("unknown setting %r (one of: %s)" % (key, ", ".join(KEYS)))
    v = str(raw).strip().lower()
    if v not in CHOICES[key]:
        raise ValueError("%s must be one of: %s (got %r)" % (key, " | ".join(CHOICES[key]), raw))
    return int(v) if key == "mantle" and v in ("1", "2") else v


def load(home):
    """Prefs with defaults filled in; anything unreadable or out of range falls back to its default."""
    doc = bus.read_json(paths.prefs_file(home))
    out = dict(DEFAULTS)
    if isinstance(doc, dict):
        for k in KEYS:
            try:
                out[k] = normalise(k, doc[k]) if k in doc else out[k]
            except ValueError:
                pass
    return out


def save(home, prefs):
    bus.atomic_write_json(paths.prefs_file(home), dict({"schema": SCHEMA}, **{k: prefs[k] for k in KEYS}))


def set_pref(home, key, raw):
    value = normalise(key, raw)
    prefs = load(home)
    prefs[key] = value
    save(home, prefs)
    return prefs


def twinkle_effective(pref, env=None):
    """(on, why). ``auto`` is off under TMUX / Ghostty / cmux or when reduced motion is requested."""
    env = os.environ if env is None else env
    if env.get("HERMES_REDUCED_MOTION") == "1":
        return False, "reduced motion requested (HERMES_REDUCED_MOTION=1): everything is static"
    if pref == "off":
        return False, "twinkle is off"
    if pref == "on":
        return True, "twinkle is on"
    if env.get("TMUX"):
        return False, "auto: off under tmux (idle repaints fight viewport restoration)"
    if (env.get("TERM_PROGRAM", "").lower() in ("ghostty", "cmux") or "ghostty" in env.get("TERM", "").lower()
            or env.get("GHOSTTY_RESOURCES_DIR") or any(k.startswith("CMUX_") for k in env)):
        return False, "auto: off under Ghostty/cmux (idle repaints fight viewport restoration)"
    return True, "auto: on (no tmux/Ghostty/cmux, no reduced motion)"
