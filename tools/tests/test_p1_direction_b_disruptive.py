"""Behaviour contract for design/directions/b-disruptive (CONTRACT.md §2/§5), via `node -e`."""
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
SIZES = {"XL": (320, 192), "M": (118, 4), "S": (24, 2)}
SIZES_BG = {"M": (118, 2), "S": (24, 1)}

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node required")

JS = """
import(process.argv[1]).then(m => {
  const a = JSON.parse(process.argv[2]);
  const r = a.calls.map(c => { const o = m.paint(c); return { px: Array.from(o.pixels), text: o.text }; });
  console.log(JSON.stringify({ r, pairs: m.authoredPairs(), meta: m.meta }));
});
"""


def run(calls):
    p = subprocess.run(["node", "-e", JS, MOD.as_uri(), json.dumps({"calls": calls})], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def sess(state):
    return next(s for s in FX["sessions"] if s["state"] == state)


def call(scale, state, session=None, t=0, size=None, **opts):
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


def test_every_scale_state_has_wh4_pixels():
    calls, dims = [], []
    for scale, (w, h) in SIZES.items():
        for st in STATES:
            calls.append(call(scale, st))
            dims.append(w * h * 4)
    for scale, (w, h) in SIZES_BG.items():
        for st in STATES:
            calls.append(call(scale, st, size=(w, h)))
            dims.append(w * h * 4)
    calls.append(call("M", "unknown", FX["degraded"]))
    dims.append(118 * 4 * 4)
    out = run(calls)
    assert [len(x["px"]) for x in out["r"]] == dims


def test_non_working_states_identical_across_t_and_working_differs():
    calls = [call("M", st, t=t) for st in STATES for t in (0, 0.25, 0.5, 0.75)]
    out = run(calls)["r"]
    for i, st in enumerate(STATES):
        frames = [out[i * 4 + k]["px"] for k in range(4)]
        if st == "working":
            assert len({tuple(f) for f in frames}) == 4, "working must differ across t"
        else:
            assert all(f == frames[0] for f in frames), f"{st} must be static"


def test_working_reduced_motion_is_static():
    out = run([call("M", "working", t=t, reducedMotion=True) for t in (0, 0.25, 0.5, 0.75, 3.0)])["r"]
    assert all(o["px"] == out[0]["px"] for o in out)


def test_working_uses_at_most_48_colours_per_frame():
    calls = [call(sc, "working", t=t / 4) for sc in SIZES for t in range(8)]
    for sess_ in FX["sessions"][:6]:
        calls.append(call("M", "working", sess_, t=0.5))
    for o in run(calls)["r"]:
        assert len(set(rgba(o["px"]))) <= 48


def test_degraded_claims_no_identity_hue():
    deg = FX["degraded"]
    calls = [call(sc, st, deg, t=0) for sc in SIZES for st in ("unknown", "idle", "working", "review")]
    for o in run(calls)["r"]:
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C > 0.03 and 110 <= H < 340), (p, C, H)


def test_alarm_text_is_literal_and_unknown_carries_question_mark():
    for scale in SIZES:
        n = run([call(scale, "needs-you"), call(scale, "fault"), call(scale, "unknown")])["r"]
        assert any(x["str"] == "INPUT 4m" or "INPUT" in x["str"] and sess("needs-you")["alarm_text"] in x["str"] for x in n[0]["text"])
        assert any(x["str"] == sess("fault")["alarm_text"] for x in n[1]["text"])
        assert any(x["str"] == "?" for x in n[2]["text"])


def test_name_label_on_m_and_s():
    for scale in ("M", "S"):
        s = sess("idle")
        t = run([call(scale, "idle", s)])["r"][0]["text"]
        assert any(x["str"] == s["name"] for x in t)


def test_authored_pairs_meet_4_5():
    pairs = run([])["pairs"]
    assert len(pairs) >= 4
    for p in pairs:
        a, b = sorted((lum(p["fg"]), lum(p["bg"])), reverse=True)
        assert (a + 0.05) / (b + 0.05) >= 4.5, p


def test_identity_pixels_stay_out_of_alarm_arc():
    sessions = FX["sessions"]
    calls = [call(sc, st, s) for s in sessions for st in ("idle", "working", "review") for sc in ("M", "S")]
    out = run(calls)["r"]
    for c, o in zip(calls, out):
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C >= 0.03 and in_arc(H)), (c["session"]["name"], c["state"], p, C, H)


def test_non_alarm_states_never_use_amber_or_red():
    sessions = FX["sessions"]
    calls = [call("M", st, s) for s in sessions for st in ("idle", "working", "review", "unknown")]
    for o in run(calls)["r"]:
        for p in set(rgba(o["px"])):
            L, C, H = oklch(p)
            assert not (C >= 0.08 and (H >= 340 or H < 100)), p


def test_states_are_structurally_distinct_per_session():
    calls = [call("M", st, sess("idle")) for st in STATES]
    out = [tuple(o["px"]) for o in run(calls)["r"]]
    assert len(set(out)) == 6
