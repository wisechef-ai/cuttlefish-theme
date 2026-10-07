"""Behaviour contract for design/directions/a-chromatophore, round 2 "Sepia dermis" (CONTRACT.md §2/§5,
vault sprint-2909/briefs/P1-round2.md D-R2-1..3).

The module is driven through `node -e` exactly as a host imports it; nothing here re-implements the painter
or reads its source. One node call renders a batch of jobs and the asserts run on the returned bytes.
"""
import base64
import json
import math
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "design" / "directions" / "a-chromatophore" / "direction.mjs"
FX = json.loads((ROOT / "tools" / "p1" / "stub-sessions.json").read_text())
STATES = FX["states"]
# XL: the real desktop pane paint (tall, D-R2-3) and a wide one; M: TUI mantle half rung; S: TUI pill
SIZES = {"XL": (133, 431), "M": (118, 4), "S": (14, 2)}
XL_WIDE = (320, 180)
M_BG = (118, 2)
M_80 = (78, 4)
SWATCH = (4, 2)          # desktop S (sidebar swatch), D-R2-2
TILE = (28, 4)           # one tile of the TUI identity grid at 120 cols (gridLayout: (118-3)//4 x 2 rows, half rung)

# `guard` replaces Math.random and Date.now with throwing stubs BEFORE the module is imported, so a direction
# that consults either fails loudly instead of passing by luck.
JS = r"""
const [, url, fxs, jobs, guard] = process.argv;
if (guard === '1') {
  Math.random = () => { throw new Error('Math.random called'); };
  Date.now = () => { throw new Error('Date.now called'); };
}
import(url).then((m) => {
  const fx = JSON.parse(fxs);
  const out = [];
  for (const j of JSON.parse(jobs)) {
    const session = j.degraded ? fx.degraded : j.idx != null ? fx.sessions[j.idx] : fx.sessions.find((s) => s.state === j.state);
    const r = m.paint({ scale: j.scale, w: j.w, h: j.h, state: j.state, session, t: j.t,
                        opts: { reducedMotion: !!j.rm, depth: 'truecolor', cssW: j.w * 4, cssH: j.h * 4 } });
    out.push({ ...j, n: r.pixels.length, ctor: r.pixels.constructor.name,
               px: Buffer.from(r.pixels.buffer, r.pixels.byteOffset, r.pixels.length).toString('base64'),
               text: r.text, alarm: session.alarm_text, name: session.name, hue: session.hue_deg });
  }
  console.log(JSON.stringify({ out, pairs: m.authoredPairs(), meta: m.meta }));
}).catch((e) => { console.error(String(e && e.stack || e)); process.exit(3); });
"""


def render(jobs, guard=False):
    r = subprocess.run(["node", "-e", JS, DIR.as_uri(), json.dumps(FX), json.dumps(jobs), "1" if guard else "0"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-2000:]
    d = json.loads(r.stdout)
    for o in d["out"]:
        o["px"] = base64.b64decode(o["px"])
    return d


def rgb(px):
    return [tuple(px[i:i + 3]) for i in range(0, len(px), 4)]


def srgb_to_oklch(r, g, b):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def lum(h):
    c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def in_arc(h):  # the identity arc [110, 340)
    return 110 <= h < 340


def hue_dist(a, b):
    return abs((a - b + 180) % 360 - 180)


def matrix(t=0.0, sizes=SIZES, **kw):
    jobs = [dict(scale=s, w=w, h=h, state=st, t=t, **kw) for s, (w, h) in sizes.items() for st in STATES]
    jobs += [dict(scale=s, w=w, h=h, state="unknown", t=t, degraded=True, **kw) for s, (w, h) in sizes.items()]
    return jobs


@pytest.fixture(scope="module")
def base():
    return render(matrix())


def test_every_scale_state_returns_wh4_pixels(base):
    assert len(base["out"]) == 3 * 7
    for o in base["out"]:
        assert o["n"] == o["w"] * o["h"] * 4, o["scale"]
        assert o["ctor"] == "Uint8ClampedArray"
    assert base["meta"]["id"] == "a-chromatophore"
    assert base["meta"]["fps"] <= 4 and base["meta"]["maxColorsWorking"] <= 48


@pytest.mark.parametrize("scale", ["XL", "M", "S"])
def test_alarm_text_literal_and_unknown_question_mark(base, scale):
    for o in base["out"]:
        if o["scale"] != scale:
            continue
        strs = [x["str"] for x in o["text"]]
        if o["state"] in ("needs-you", "fault"):
            assert o["alarm"] in strs, (o["state"], strs)
        if o["state"] == "unknown":
            assert "?" in strs
        if scale in ("M", "S") and not o.get("degraded") and o["state"] not in ("needs-you", "fault"):
            assert o["name"] in strs, (o["state"], strs)


def test_alarm_text_fits_80_cols_and_bg_rung_with_the_name():
    jobs = [dict(scale="M", w=w, h=h, state=st, t=0) for (w, h) in (M_80, M_BG) for st in ("needs-you", "fault")]
    for o in render(jobs)["out"]:
        txt = [x for x in o["text"] if x["str"] == o["alarm"]]
        assert txt and txt[0]["x"] >= 0 and txt[0]["x"] + len(o["alarm"]) <= o["w"]
        assert o["name"] in [x["str"] for x in o["text"]]


@pytest.mark.parametrize("st", [s for s in STATES if s != "working"])
def test_non_working_states_identical_across_t(st):
    sizes = {**SIZES, "XLw": XL_WIDE}
    jobs = [dict(scale=s[:2] if s.startswith("XL") else s, w=w, h=h, state=st, t=t, key=s)
            for s, (w, h) in sizes.items() for t in (0, 0.25, 0.5, 0.75, 3.1)]
    by = {}
    for o in render(jobs)["out"]:
        by.setdefault(o["key"], set()).add(o["px"])
    assert all(len(v) == 1 for v in by.values()), {k: len(v) for k, v in by.items()}


@pytest.mark.parametrize("scale", ["XL", "M", "S"])
def test_working_animates_within_the_colour_budget(scale):
    w, h = SIZES[scale]
    frames = render([dict(scale=scale, w=w, h=h, state="working", t=t) for t in (0, 0.25, 0.5, 0.75, 1.0, 2.0)])["out"]
    assert len({f["px"] for f in frames}) >= 4, scale
    for f in frames:
        assert len(set(rgb(f["px"]))) <= 48, (scale, f["t"], len(set(rgb(f["px"]))))
    rm = render([dict(scale=scale, w=w, h=h, state="working", t=t, rm=True) for t in (0, 0.5, 2.0)])["out"]
    assert len({f["px"] for f in rm}) == 1          # reduced motion: fully static


def test_working_holds_still_within_a_quarter_second():
    # <= 4 fps: frames inside one 0.25 s step are byte-identical
    frames = render([dict(scale="M", w=118, h=4, state="working", t=t) for t in (0.5, 0.56, 0.62, 0.74)])["out"]
    assert len({f["px"] for f in frames}) == 1


def test_desktop_swatch_moves_at_4x2_and_carries_no_text():
    w, h = SWATCH
    frames = render([dict(scale="S", w=w, h=h, state="working", t=t) for t in (0, 0.25, 0.5, 0.75)])["out"]
    assert len({f["px"] for f in frames}) >= 3
    every = render(matrix(sizes={"S": SWATCH}))["out"]
    assert all(o["text"] == [] for o in every)


def test_degraded_claims_no_identity_hue(base):
    for o in base["out"]:
        if not o.get("degraded"):
            continue
        for r, g, b in rgb(o["px"]):
            L, C, h = srgb_to_oklch(r, g, b)
            assert not (in_arc(h) and C > 0.03), (o["scale"], (r, g, b), round(C, 3), round(h))


@pytest.mark.parametrize("st", ["idle", "working", "review"])
def test_identity_states_use_no_alarm_colour(st):
    # every coloured pixel of a non-alarm state is identity: it must live inside the identity arc, for every
    # session (the arc ends at 110 and 340 are the hardest)
    jobs = [dict(scale=s, w=w, h=h, state=st, t=t, idx=i) for s, (w, h) in SIZES.items() for t in (0, 1.5) for i in (0, 16)]
    for o in render(jobs)["out"]:
        for r, g, b in rgb(o["px"]):
            L, C, h = srgb_to_oklch(r, g, b)
            if C >= 0.03:
                assert in_arc(h), (st, o["scale"], o["idx"], (r, g, b), round(C, 3), round(h))


def test_identity_hue_owns_the_majority_of_an_idle_tile():
    # D-R2-1: the tile median must carry the hue, so the hue must own > 50 % of the tile's pixels
    w, h = TILE
    for o in render([dict(scale="S", w=w, h=h, state="idle", t=0, idx=i) for i in range(len(FX["sessions"]))])["out"]:
        own = sum(1 for p in rgb(o["px"]) if (lambda L, C, hh: C >= 0.05 and hue_dist(hh, o["hue"]) <= 20)(*srgb_to_oklch(*p)))
        assert own / (w * h) > 0.5, (o["idx"], o["name"], own / (w * h))


def test_authored_pairs_meet_contrast_and_cover_every_text(base):
    pairs = base["pairs"]
    assert pairs
    for p in pairs:
        assert contrast(p["fg"], p["bg"]) >= 4.5, p
    allowed = {(p["fg"].lower(), p["bg"].lower()) for p in pairs}
    for o in base["out"]:
        for x in o["text"]:
            assert (x["fg"].lower(), x["bg"].lower()) in allowed, x


def test_states_are_structurally_distinct():
    d = render([dict(scale="M", w=118, h=4, state=s, t=0) for s in STATES])["out"]
    assert len({o["px"] for o in d}) == 6


def test_needs_you_and_fault_differ_in_structure_not_only_colour():
    # INPUT vs ERROR must survive the loss of hue (CVD, 256): compare the lightness maps
    d = {o["state"]: o for o in render([dict(scale="M", w=118, h=4, state=s, t=0) for s in ("needs-you", "fault")])["out"]}
    Ls = {k: [srgb_to_oklch(*p)[0] for p in rgb(o["px"])] for k, o in d.items()}
    dark = {k: sum(1 for L in v if L < 0.5) / len(v) for k, v in Ls.items()}
    assert dark["needs-you"] > 2 * dark["fault"] + 0.1, dark     # zebra is barred dark; deimatic is blanched


def test_deterministic_without_random_or_clock():
    jobs = matrix(t=0.5) + [dict(scale="S", w=4, h=2, state="working", t=0.25)]
    a = render(jobs, guard=True)["out"]
    b = render(jobs)["out"]
    assert [o["px"] for o in a] == [o["px"] for o in b]
