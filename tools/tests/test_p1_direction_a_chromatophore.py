"""Behaviour contract for design/directions/a-chromatophore (CONTRACT.md §2/§5).

The module is invoked through `node -e` exactly as a host would import it; nothing here
re-implements the painter. One node call renders the whole matrix and the asserts run on JSON.
"""
import json
import math
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "design" / "directions" / "a-chromatophore" / "direction.mjs"
FX = json.loads((ROOT / "tools" / "p1" / "stub-sessions.json").read_text())
STATES = FX["states"]
SIZES = {"XL": (320, 180), "M": (118, 4), "S": (14, 2)}
M_BG = (118, 2)
M_80 = (78, 4)

JS = r"""
const m = await import(process.argv[1]);
const fx = JSON.parse(process.argv[2]);
const job = JSON.parse(process.argv[3]);
const out = [];
for (const j of job) {
  const session = j.degraded ? fx.degraded : fx.sessions.find(s => s.state === j.state);
  const r = m.paint({ scale: j.scale, w: j.w, h: j.h, state: j.state, session, t: j.t,
                      opts: { reducedMotion: !!j.rm, depth: 'truecolor' } });
  out.push({ ...j, n: r.pixels.length, ctor: r.pixels.constructor.name,
             px: Buffer.from(r.pixels.buffer, r.pixels.byteOffset, r.pixels.length).toString('base64'),
             text: r.text, alarm: session.alarm_text, name: session.name });
}
const extra = { pairs: m.authoredPairs(), meta: m.meta };
console.log(JSON.stringify({ out, extra }));
"""


def render(job):
    import base64
    wrapper = "import(process.argv[1]).then(async m=>{" + JS.replace("const m = await import(process.argv[1]);", "") + "})"
    r = subprocess.run(["node", "-e", wrapper, DIR.as_uri(), json.dumps(FX), json.dumps(job)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-2000:]
    d = json.loads(r.stdout)
    for o in d["out"]:
        o["px"] = base64.b64decode(o["px"])
    return d


def rgba(px):
    return [tuple(px[i:i + 4]) for i in range(0, len(px), 4)]


def srgb_to_oklch(r, g, b):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def in_arc(h):  # the identity arc [110, 340)
    return 110 <= h < 340


def matrix(t=0.0, **kw):
    jobs = [dict(scale=s, w=w, h=h, state=st, t=t, **kw) for s, (w, h) in SIZES.items() for st in STATES]
    jobs += [dict(scale=s, w=w, h=h, state="unknown", t=t, degraded=True, **kw) for s, (w, h) in SIZES.items()]
    return jobs


def test_every_scale_state_returns_wh4_pixels_and_literal_text():
    d = render(matrix())
    assert len(d["out"]) == 3 * 7
    for o in d["out"]:
        assert o["n"] == o["w"] * o["h"] * 4, o["scale"]
        assert o["ctor"] == "Uint8ClampedArray"
    assert d["extra"]["meta"]["id"] == "a-chromatophore"
    assert d["extra"]["meta"]["fps"] <= 4 and d["extra"]["meta"]["maxColorsWorking"] <= 48


@pytest.mark.parametrize("scale", ["XL", "M", "S"])
def test_alarm_text_literal_and_unknown_question_mark(scale):
    d = render(matrix())
    for o in d["out"]:
        if o["scale"] != scale:
            continue
        strs = [x["str"] for x in o["text"]]
        if o["state"] in ("needs-you", "fault"):
            assert o["alarm"] in strs, (o["state"], strs)
        if o["state"] == "unknown":
            assert "?" in strs
        if scale in ("M", "S") and not o.get("degraded") and o["state"] not in ("needs-you", "fault"):
            assert o["name"] in strs, (o["state"], strs)


def test_alarm_text_fits_80_cols():
    jobs = [dict(scale="M", w=w, h=h, state=st, t=0) for (w, h) in (M_80, M_BG) for st in ("needs-you", "fault")]
    for o in render(jobs)["out"]:
        txt = [x for x in o["text"] if x["str"] == o["alarm"]]
        assert txt and txt[0]["x"] >= 0 and txt[0]["x"] + len(o["alarm"]) <= o["w"]
        # name label is kept alongside the alarm at 80 cols (pattern must still be visible)
        assert o["name"] in [x["str"] for x in o["text"]]


@pytest.mark.parametrize("st", [s for s in STATES if s != "working"])
def test_non_working_states_identical_across_t(st):
    jobs = [dict(scale=s, w=w, h=h, state=st, t=t) for s, (w, h) in SIZES.items() for t in (0, 0.25, 0.5, 0.75, 3.1)]
    by = {}
    for o in render(jobs)["out"]:
        by.setdefault(o["scale"], set()).add(o["px"])
    assert all(len(v) == 1 for v in by.values())


def test_working_animates_within_budget():
    frames = render([dict(scale="M", w=118, h=4, state="working", t=t) for t in (0, 0.25, 0.5, 0.75, 1.0, 2.0)])["out"]
    assert len({f["px"] for f in frames}) >= 4
    for f in frames:
        assert len(set(rgba(f["px"]))) <= 48
    # reduced motion: fully static
    rm = render([dict(scale="M", w=118, h=4, state="working", t=t, rm=True) for t in (0, 0.5, 2.0)])["out"]
    assert len({f["px"] for f in rm}) == 1


def test_degraded_claims_no_identity_hue():
    for o in render(matrix())["out"]:
        if not o.get("degraded"):
            continue
        for r, g, b, a in rgba(o["px"]):
            L, C, h = srgb_to_oklch(r, g, b)
            assert not (in_arc(h) and C > 0.03), (o["scale"], (r, g, b), round(C, 3), round(h))


@pytest.mark.parametrize("st", ["idle", "working", "review"])
def test_identity_pixels_outside_alarm_arc(st):
    # every coloured pixel on these states is identity: it must live inside the identity arc
    jobs = [dict(scale=s, w=w, h=h, state=st, t=t) for s, (w, h) in SIZES.items() for t in (0, 0.5, 1.5)]
    for o in render(jobs)["out"]:
        for r, g, b, a in rgba(o["px"]):
            L, C, h = srgb_to_oklch(r, g, b)
            if C >= 0.03:
                assert in_arc(h), (st, o["scale"], (r, g, b), round(C, 3), round(h))
    # and it really is the session hue (not a flat grey)
    d = render(jobs[:1])["out"][0]
    assert any(srgb_to_oklch(*p[:3])[1] >= 0.08 for p in rgba(d["px"]))


def test_pairs_and_rendered_text_pairs_contrast():
    d = render(matrix())
    pairs = d["extra"]["pairs"]
    assert pairs
    for p in pairs:
        assert contrast(p["fg"], p["bg"]) >= 4.5, p
    allowed = {(p["fg"].lower(), p["bg"].lower()) for p in pairs}
    for o in d["out"]:
        for x in o["text"]:
            assert (x["fg"].lower(), x["bg"].lower()) in allowed, x


def test_states_are_structurally_distinct():
    # same session hue is not available across states, so compare structure: row-0 pixel sequences differ
    d = render([dict(scale="M", w=118, h=4, state=s, t=0) for s in STATES])["out"]
    assert len({o["px"] for o in d}) == 6
