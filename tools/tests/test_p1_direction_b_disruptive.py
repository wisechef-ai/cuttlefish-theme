"""Behaviour contract for design/directions/b-disruptive (CONTRACT.md §2/§5, briefs/P1-round2.md D-R2-1/2), via `node -e`.

Every assertion is on paint() output (pixels / text overlays) or authoredPairs(); no test reads source text.
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "design" / "directions" / "b-disruptive" / "direction.mjs"
FX = json.loads((ROOT / "tools" / "p1" / "stub-sessions.json").read_text())
STATES = ["idle", "working", "review", "needs-you", "fault", "unknown"]
SIZES = {"XL": (180, 286), "M": (118, 4), "S": (14, 2)}          # XL ~ a 720x1145 pane / 4; S = the TUI pill
SIZES_BG = {"M": (118, 2), "S": (14, 1)}                          # the TUI bg rung (one px per tall cell)
SWATCH = (4, 2)                                                   # desktop sidebar swatch (D-R2-2)
TILE = (28, 4)                                                    # one tile of the TUI 16/20 identity grid at 120 cols

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node required")

# Math.random and Date.now throw inside the paint process: a direction that depends on either fails loudly.
JS = """
Math.random = () => { throw new Error('Math.random used'); };
Date.now = () => { throw new Error('Date.now used'); };
import(process.argv[1]).then(m => {
  const a = JSON.parse(process.argv[2]);
  const r = a.calls.map(c => { const o = m.paint(c); return { px: Array.from(o.pixels), text: o.text }; });
  console.log(JSON.stringify({ r, pairs: m.authoredPairs(), meta: m.meta }));
});
"""


def run(calls):
    p = subprocess.run(["node", "-e", JS, MOD.as_uri(), json.dumps({"calls": calls})], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def sess(state):
    return next(s for s in FX["sessions"] if s["state"] == state)


def call(scale, state, session=None, t=0.0, size=None, **opts):
    w, h = size or SIZES[scale]
    return dict(scale=scale, w=w, h=h, state=state, session=session or sess(state), t=t,
                opts={"reducedMotion": False, "depth": "truecolor", **opts})


def rgba(px):
    return [tuple(px[i:i + 4]) for i in range(0, len(px), 4)]


def oklch(rgb):
    f = lambda c: ((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92
    r, g, b = map(f, rgb[:3])
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def in_arc(hue):  # the alarm arc [340, 110) wraps through 0
    return hue >= 340 or hue < 110


def lum(hexs):
    c = [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def hue_dist(a, b):
    return abs((a - b + 180) % 360 - 180)


def test_every_scale_state_has_wh4_pixels():
    calls, dims = [], []
    for scale, (w, h) in list(SIZES.items()) + list(SIZES_BG.items()) + [("S", SWATCH), ("S", TILE)]:
        for st in STATES:
            calls.append(call(scale, st, size=(w, h)))
            dims.append(w * h * 4)
    calls.append(call("M", "unknown", FX["degraded"]))
    dims.append(118 * 4 * 4)
    out = run(calls)
    assert [len(x["px"]) for x in out["r"]] == dims


def test_non_working_states_identical_across_t_and_working_differs():
    for scale in ("M", "XL"):
        calls = [call(scale, st, t=t) for st in STATES for t in (0, 0.25, 0.5, 0.75)]
        out = run(calls)["r"]
        for i, st in enumerate(STATES):
            frames = [out[i * 4 + k]["px"] for k in range(4)]
            if st == "working":
                assert len({tuple(f) for f in frames}) == 4, f"{scale} working must differ across t"
            else:
                assert all(f == frames[0] for f in frames), f"{scale} {st} must be static"


def test_working_reduced_motion_is_static():
    out = run([call("M", "working", t=t, reducedMotion=True) for t in (0, 0.25, 0.5, 0.75, 3.0)])["r"]
    assert all(o["px"] == out[0]["px"] for o in out)


def test_working_moves_at_most_4_fps():
    # frames inside one 0.25 s step are identical: the clock is quantised to <= 4 fps
    out = run([call("M", "working", t=t) for t in (1.0, 1.1, 1.24)])["r"]
    assert out[0]["px"] == out[1]["px"] == out[2]["px"]


def test_working_uses_at_most_48_colours_per_frame():
    calls = [call(sc, "working", t=t / 4) for sc in SIZES for t in range(8)]
    calls += [call("S", "working", t=t / 4, size=SWATCH) for t in range(4)]
    for s in FX["sessions"][:6]:
        calls.append(call("M", "working", s, t=0.5))
        calls.append(call("XL", "working", s, t=0.75))
    for o in run(calls)["r"]:
        assert len(set(rgba(o["px"]))) <= 48


def test_desktop_swatch_working_moves_and_carries_no_text():
    for s in FX["sessions"]:
        out = run([call("S", "working", s, t=t, size=SWATCH) for t in (0, 0.25, 0.5, 0.75)])["r"]
        assert len({tuple(o["px"]) for o in out}) >= 3, s["name"]
        assert all(o["text"] == [] for o in out)
    others = run([call("S", st, size=SWATCH) for st in STATES])["r"]
    assert all(o["text"] == [] for o in others)


def test_degraded_claims_no_identity_hue():
    deg = FX["degraded"]
    sizes = list(SIZES.items()) + [("S", SWATCH), ("M", SIZES_BG["M"])]
    calls = [call(sc, st, deg, t=0, size=wh) for sc, wh in sizes for st in ("unknown", "idle", "working", "review")]
    for o in run(calls)["r"]:
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C > 0.03 and 110 <= H < 340), (p, C, H)


def test_alarm_text_is_literal_on_m_pill_and_xl_and_unknown_carries_question_mark():
    for scale in SIZES:
        n = run([call(scale, "needs-you"), call(scale, "fault"), call(scale, "unknown")])["r"]
        assert any(x["str"] == sess("needs-you")["alarm_text"] for x in n[0]["text"]), scale
        assert any(x["str"] == sess("fault")["alarm_text"] for x in n[1]["text"]), scale
        assert any(x["str"] == "?" for x in n[2]["text"]), scale
    # the 80-col mantle (78 px) still carries the literal alarm text
    n = run([call("M", "needs-you", size=(78, 4)), call("M", "fault", size=(78, 2))])["r"]
    assert any(x["str"] == "INPUT 4m" for x in n[0]["text"]) and any(x["str"] == "ERROR 2m" for x in n[1]["text"])


def test_name_label_on_m_and_pill():
    for scale in ("M", "S"):
        s = sess("idle")
        t = run([call(scale, "idle", s)])["r"][0]["text"]
        assert any(x["str"] == s["name"] for x in t)
    t = run([call("M", "unknown", FX["degraded"])])["r"][0]["text"]
    assert any(x["str"] == "unbound" for x in t)


def test_text_fits_inside_the_strip():
    for scale, (w, h) in [("M", (78, 4)), ("M", (118, 2)), ("S", (14, 2))]:
        for o in run([call(scale, st, size=(w, h)) for st in STATES])["r"]:
            for x in o["text"]:
                assert 0 <= x["x"] and x["x"] + len(x["str"]) <= w and 0 <= x["y"] < max(1, h // 2 if h >= 2 else 1) + 1


def test_authored_pairs_meet_4_5():
    pairs = run([])["pairs"]
    assert len(pairs) >= 4
    for p in pairs:
        a, b = sorted((lum(p["fg"]), lum(p["bg"])), reverse=True)
        assert (a + 0.05) / (b + 0.05) >= 4.5, p


def test_identity_pixels_stay_out_of_alarm_arc():
    calls = [call(sc, st, s) for s in FX["sessions"] for st in ("idle", "working", "review") for sc in ("M", "S")]
    out = run(calls)["r"]
    for c, o in zip(calls, out):
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C >= 0.03 and in_arc(H)), (c["session"]["name"], c["state"], p, C, H)


def test_non_alarm_states_never_use_amber_or_red():
    calls = [call(sc, st, s) for s in FX["sessions"] for st in ("idle", "working", "review", "unknown") for sc in ("M", "XL")]
    for o in run(calls)["r"]:
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C >= 0.08 and (H >= 340 or H < 100)), p


def test_identity_hue_owns_the_majority_of_an_idle_tile():
    """D-R2-1: in an idle S tile (identity-grid tile and desktop swatch) more than half of the pigment pixels
    (text cells excluded) carry the session's own hue with real chroma."""
    for size in (TILE, SWATCH):
        out = run([call("S", "idle", s, size=size) for s in FX["sessions"]])["r"]
        for s, o in zip(FX["sessions"], out):
            w, h = size
            masked = set()
            for x in o["text"]:
                for cx in range(x["x"], x["x"] + len(x["str"])):
                    masked |= {(cx, 2 * x["y"]), (cx, 2 * x["y"] + 1)}
            px = rgba(o["px"])
            keep = [px[y * w + x] for y in range(h) for x in range(w) if (x, y) not in masked]
            own = sum(1 for p in keep if oklch(p)[1] >= 0.06 and hue_dist(oklch(p)[2], s["hue_deg"]) <= 20)
            assert own / len(keep) > 0.5, (size, s["name"], own, len(keep))


def test_identity_tiles_separate_nearest_neighbours():
    """The 20 fixture sessions' idle tiles (median OKLab, text excluded) stay >= 0.020 apart: the G2 identity rule
    measured on the paint output, so a redesign cannot silently collapse neighbouring hues."""
    out = run([call("S", "idle", s, size=TILE) for s in FX["sessions"]])["r"]
    w, h = TILE
    meds = []
    for o in out:
        masked = {(cx, yy) for x in o["text"] for cx in range(x["x"], x["x"] + len(x["str"])) for yy in (0, 1)}
        px = rgba(o["px"])
        labs = []
        for y in range(h):
            for x in range(w):
                if (x, y) in masked:
                    continue
                L, C, H = oklch(px[y * w + x])
                labs.append((L, C * math.cos(math.radians(H)), C * math.sin(math.radians(H))))
        meds.append([sorted(v)[len(v) // 2] for v in zip(*labs)])
    worst = min(math.dist(meds[i], meds[j]) for i in range(len(meds)) for j in range(i + 1, len(meds)))
    assert worst >= 0.020, worst


def test_states_are_structurally_distinct_per_session():
    for scale, size in (("M", (118, 4)), ("M", (118, 2)), ("XL", SIZES["XL"])):
        calls = [call(scale, st, sess("idle"), size=size) for st in STATES]
        out = [tuple(o["px"]) for o in run(calls)["r"]]
        assert len(set(out)) == 6


def test_deterministic_same_args_same_bytes():
    calls = [call(sc, st, t=0.5) for sc in SIZES for st in STATES]
    a, b = run(calls)["r"], run(list(reversed(calls)))["r"]
    assert [o["px"] for o in a] == [o["px"] for o in reversed(b)]
