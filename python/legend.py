"""``hermes cuttlefish legend``: the 7 states + degraded (CONTEXT-D2 §0): the pattern, what triggers it, what to DO.

Colour only on a TTY (never under NO_COLOR or a pipe), foreground only (never a bg SGR). Every colour value comes
from ``packages/core/tokens.json``; nothing is derived here beyond OKLCH -> sRGB through the repo's own converter."""
import importlib.util
import json
import os
import sys

from . import surfaces

STATES = (
    # id, pattern, trigger, what to do
    ("idle", "calm tone; a rare twinkle, about one dot per 1.5 s (only when twinkle allows)",
     "no turn running, nothing waiting", "Nothing. Type when you like."),
    ("thinking", "soft clouds drifting left to right, about 6 s per crossing",
     "the model is working (pre_llm_call .. next tool or end)", "Wait, or keep typing: it will not block you."),
    ("tool", "sparkle bursts with a pale glint at the peak",
     "a tool is running (not clarify)", "Wait. A long tool run is normal."),
    ("review", "a still mottle of soft blotches, no motion",
     "a verification pass just finished", "Nothing. It settles to idle by itself."),
    ("needs-you", "dots settle low; amber eyespots pulse together; the text 'INPUT <age>' where text fits",
     "a clarify question or an approval is waiting", "Answer it. The agent cannot continue without you."),
    ("fault", "everything blanches, then red dots hold still; the text 'ERROR <age>'",
     "a non-retryable API error (sticky until the next turn starts)", "Read the error; send a message to retry."),
    ("unknown", "sparse grey dots, still; the text '?'",
     "no live owner, a stale heartbeat, or the session ended", "Nothing is wrong with you. Start or resume a session."),
    ("degraded", "like unknown; the label reads 'unbound'",
     "this surface cannot tell which session it belongs to", "Run: hermes cuttlefish doctor (the binding row)."),
)


def _load_oklab():
    name = "_cf_oklab"
    if name not in sys.modules:
        p = surfaces.PKG_ROOT / "color" / "oklab.py"
        spec = importlib.util.spec_from_file_location(name, p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def _tokens():
    with open(surfaces.PKG_ROOT / "packages" / "core" / "tokens.json", encoding="utf-8") as f:
        return json.load(f)


def _fg(rgb):
    return "\033[38;2;%d;%d;%dm" % tuple(rgb)


def palette():
    """state id -> (r, g, b) for the swatch. Identity states use one sample hue from the arc at the mid tier."""
    ok, t = _load_oklab(), _tokens()
    ident = t["identity"]
    mid_hue = sum(ident["hue_arc_deg"]) / 2
    hexv = ok.oklch_to_hex(ok.OKLCh(ident["dot_lightness"][1], ident["dot_chroma"], mid_hue))
    ident_rgb = tuple(int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    amber, red = t["alarm"]["amber"]["rgb"], t["alarm"]["red"]["rgb"]
    grey = tuple(int(ok.oklch_to_hex(ok.OKLCh(0.55, 0.0, 0.0))[i:i + 2], 16) for i in (1, 3, 5))
    return {"idle": ident_rgb, "thinking": ident_rgb, "tool": ident_rgb, "review": ident_rgb,
            "needs-you": tuple(amber), "fault": tuple(red), "unknown": grey, "degraded": grey}


def use_color(stream=None, env=None):
    stream = sys.stdout if stream is None else stream
    env = os.environ if env is None else env
    return bool(getattr(stream, "isatty", lambda: False)()) and not env.get("NO_COLOR") and env.get("TERM") != "dumb"


def run(out=print, color=None):
    color = use_color() if color is None else color
    pal = palette() if color else {}
    out("cuttlefish legend: 7 states + degraded. Dots only; your terminal background is never touched.")
    out("  ladder:  (blank) < ·  < •  < ●   a dot opens as it matters")
    for sid, pattern, trigger, todo in STATES:
        sw = "· • ●"
        if color:
            sw = _fg(pal[sid]) + sw + "\033[0m"
        out("")
        out("  %-10s %s" % (sid, sw))
        out("    looks like : %s" % pattern)
        out("    when       : %s" % trigger)
        out("    you        : %s" % todo)
    return 0
