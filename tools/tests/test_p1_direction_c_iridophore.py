"""Behaviour contract for direction C (design/directions/c-iridophore/direction.mjs).

The module is exercised exactly as a host would: imported by Node and painted against the shared
fixture. Every assertion is about the returned pixels/text, never the source text (CONTRACT §2, §5).
"""
import base64
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIRECTION = ROOT / "design" / "directions" / "c-iridophore" / "direction.mjs"
FX = json.loads((ROOT / "tools" / "p1" / "stub-sessions.json").read_text())
STATES = FX["states"]
# Sizes a host actually asks for: TUI mantle at 120/80 cols on the half (×4) and bg (×2) rungs,
# 1-row mantle, the desktop chip (22×2), the TUI pill (14×2 / 14×1), the desktop swatch (4×2) and
# XL field panes at the round-2 low internal resolution (CONTRACT §2: w*h <= 57600).
SIZES = {"XL": [(133, 431), (180, 120)], "M": [(118, 4), (118, 2), (78, 4), (78, 2), (118, 1), (22, 2)],
         "S": [(14, 2), (14, 1), (4, 2)]}
PILL = [(14, 2), (14, 1)]
SWATCH = (4, 2)

RUNNER = r"""
import { pathToFileURL } from 'node:url';
const [path, reqJson] = process.argv.slice(1);
const mod = await import(pathToFileURL(path).href);
const reqs = JSON.parse(reqJson);
const out = reqs.map(r => {
  const res = mod.paint(r);
  const px = res.pixels;
  return { ok: px instanceof Uint8ClampedArray, len: px.length,
           b64: Buffer.from(px.buffer, px.byteOffset, px.length).toString('base64'), text: res.text };
});
const pairs = typeof mod.authoredPairs === 'function' ? mod.authoredPairs() : null;
process.stdout.write(JSON.stringify({ meta: mod.meta, out, pairs }));
"""


def _session(state, idx=0):
    if state == "degraded":
        return FX["degraded"]
    return [s for s in FX["sessions"] if s["state"] == state][idx]


def paint_many(reqs):
    r = subprocess.run(["node", "--input-type=module", "-e", RUNNER, str(DIRECTION), json.dumps(reqs)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def req(scale, w, h, state, session, t=0.0, reduced=False, depth="truecolor"):
    return {"scale": scale, "w": w, "h": h, "state": state, "session": session, "t": t,
            "opts": {"reducedMotion": reduced, "depth": depth}}


def pixels(o):
    b = base64.b64decode(o["b64"])
    return [tuple(b[i:i + 3]) for i in range(0, len(b), 4)]


# ---- OKLab (Björn Ottosson) ----
def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklch(rgb):
    r, g, b = (_lin(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def rel_lum(hexc):
    v = [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
    r, g, b = (_lin(c) for c in v)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def in_alarm_arc(h):
    return h >= 340 or h < 110


ALL_STATES = STATES + ["degraded"]


@lru_cache(maxsize=1)
def matrix():
    """Every (scale, size, state) at t=0 and t=1.7 (reducedMotion off)."""
    keys, reqs = [], []
    for scale, sizes in SIZES.items():
        for (w, h) in sizes:
            for st in ALL_STATES:
                sess = _session(st)
                paint_state = "unknown" if st == "degraded" else st
                for t in (0.0, 1.7):
                    keys.append((scale, w, h, st, t))
                    reqs.append(req(scale, w, h, paint_state, sess, t))
    res = paint_many(reqs)
    return dict(zip(keys, res["out"])), res


def test_meta_matches_contract():
    _, res = matrix()
    m = res["meta"]
    assert m["id"] == "c-iridophore"
    assert m["maxColorsWorking"] <= 48 and 0 < m["fps"] <= 4


@pytest.mark.parametrize("scale", list(SIZES))
def test_every_scale_state_returns_full_rgba_buffer(scale):
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if sc == scale:
            assert o["ok"], (sc, w, h, st)
            assert o["len"] == w * h * 4, (sc, w, h, st, o["len"])


def test_non_working_states_are_static_across_t():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if st != "working" and t == 0.0:
            assert o["b64"] == mx[(sc, w, h, st, 1.7)]["b64"], (sc, w, h, st)


def test_working_animates_with_bounded_palette():
    sess = _session("working")
    ts = [0.0, 0.25, 0.5, 0.75, 1.7]
    reqs = [req(sc, w, h, "working", sess, t) for sc, sizes in SIZES.items() for (w, h) in sizes for t in ts]
    out = paint_many(reqs)["out"]
    i = 0
    for sc, sizes in SIZES.items():
        for (w, h) in sizes:
            frames = out[i:i + len(ts)]
            i += len(ts)
            for f in frames:
                assert len(set(pixels(f))) <= 48, (sc, w, h)
            if (w, h) not in PILL:  # a 14-px pill may show a still part of the cloud
                assert len({f["b64"] for f in frames}) > 1, (sc, w, h)


def test_desktop_swatch_working_moves_visibly_at_4x2():
    """D-R2-2 / plan 13.4 #7: the 4x2 swatch shows >= 3 distinct frames among t = 0, .25, .5, .75 (every session)."""
    reqs = [req("S", *SWATCH, "working", s, t) for s in FX["sessions"] for t in (0.0, 0.25, 0.5, 0.75)]
    out = paint_many(reqs)["out"]
    for k, s in enumerate(FX["sessions"]):
        frames = out[k * 4:(k + 1) * 4]
        assert len({f["b64"] for f in frames}) >= 3, s["name"]


def test_desktop_swatch_carries_no_text():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if sc == "S" and (w, h) == SWATCH:
            assert o["text"] == [], (st, o["text"])


def test_same_arguments_give_the_same_bytes():
    """Pure: no Math.random / Date.now. Painting the same request twice in separate processes is byte-identical."""
    reqs = [req(sc, w, h, st, _session(st), 0.6) for sc, sizes in SIZES.items() for (w, h) in sizes[:1]
            for st in STATES]
    a, b = paint_many(reqs)["out"], paint_many(list(reversed(reqs)))["out"]
    assert [o["b64"] for o in a] == [o["b64"] for o in reversed(b)]
    assert [o["text"] for o in a] == [o["text"] for o in reversed(b)]


def _owns_identity(p, hue):
    L, C, H = oklch(p)
    d = abs((H - hue + 180) % 360 - 180)
    return C >= 0.06 and d <= 30


def test_identity_hue_owns_most_of_an_idle_tile():
    """D-R2-1: the identity hue owns > 50 % of every idle S tile (identity grid tile 28x4, pill, swatch)."""
    reqs, keys = [], []
    for s in FX["sessions"]:
        for (w, h) in [(28, 4), (14, 2), SWATCH]:
            keys.append((s["name"], w, h, s["hue_deg"]))
            reqs.append(req("S", w, h, "idle", s))
    out = paint_many(reqs)["out"]
    for (name, w, h, hue), o in zip(keys, out):
        px = pixels(o)
        # text cells are masked by G2; mask them here too (cell coords: each cell is 2 px tall on h=2*rows)
        rows = h // 2 if h >= 2 else 1
        masked = set()
        for x in o["text"]:
            for c in range(x["x"], x["x"] + len(x["str"])):
                for yy in range(x["y"] * (h // rows), (x["y"] + 1) * (h // rows)):
                    masked.add(yy * w + c)
        keep = [p for i, p in enumerate(px) if i not in masked]
        share = sum(_owns_identity(p, hue) for p in keep) / max(1, len(keep))
        assert share > 0.5, (name, w, h, round(share, 2))


def test_reduced_motion_freezes_working():
    sess = _session("working")
    out = paint_many([req("M", 118, 4, "working", sess, t, reduced=True) for t in (0.0, 0.5, 3.0)])["out"]
    assert len({o["b64"] for o in out}) == 1


def test_degraded_claims_no_identity_hue():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if st != "degraded":
            continue
        for p in set(pixels(o)):
            L, C, H = oklch(p)
            assert C < 0.03 or in_alarm_arc(H), (sc, w, h, p, C, H)
        strs = " ".join(x["str"] for x in o["text"])
        if (w, h) != SWATCH:  # the swatch carries no text (D-R2-2)
            assert "?" in strs, (sc, strs)


def test_identity_states_never_use_alarm_hues():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if st not in ("idle", "working", "review"):
            continue
        for p in set(pixels(o)):
            L, C, H = oklch(p)
            assert C < 0.03 or not in_alarm_arc(H), (sc, w, h, st, p, round(C, 3), round(H, 1))


def test_alarm_text_is_literal_and_unknown_carries_question_mark():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if sc == "S" and (w, h) == SWATCH:
            continue  # the swatch carries no text (D-R2-2)
        strs = [x["str"] for x in o["text"]]
        joined = " ".join(strs)
        if st in ("needs-you", "fault"):
            assert _session(st)["alarm_text"] in joined, (sc, w, h, st, strs)
        if st == "unknown":
            assert "?" in joined, (sc, w, h, strs)


def test_alarm_text_is_verbatim_on_every_alarm_pill_and_mantle():
    """Every fixture alarm session, on the TUI pill and the 80/120-col mantles: alarm_text appears as one string."""
    alarms = [s for s in FX["sessions"] if s["alarm_text"]]
    sizes = PILL + [(118, 4), (78, 4), (78, 2), (22, 2)]
    reqs = [req("S" if (w, h) in PILL else "M", w, h, s["state"], s) for s in alarms for (w, h) in sizes]
    out = paint_many(reqs)["out"]
    k = 0
    for s in alarms:
        for (w, h) in sizes:
            strs = [x["str"].strip() for x in out[k]["text"]]
            k += 1
            assert s["alarm_text"] in strs, (s["name"], w, h, strs)
            for x in out[k - 1]["text"]:
                assert 0 <= x["x"] and x["x"] + len(x["str"]) <= w, (s["name"], w, h, x)


def test_m_and_s_carry_the_session_name_when_room():
    """The mantle always names the session; the pill names it unless an alarm plate needs the room (L7 first)."""
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if (sc == "S" and (w, h) == SWATCH) or (sc == "S" and st in ("needs-you", "fault")):
            continue
        if sc in ("M", "S"):
            name = _session(st)["name"]
            joined = " ".join(x["str"] for x in o["text"])
            assert name in joined, (sc, w, h, st, joined)


def test_text_fits_inside_the_canvas_at_80_cols():
    mx, _ = matrix()
    for (sc, w, h, st, t), o in mx.items():
        if sc in ("M", "S"):
            for x in o["text"]:
                assert 0 <= x["y"] < h and 0 <= x["x"] and x["x"] + len(x["str"]) <= w, (w, h, st, x)


def test_authored_pairs_meet_4_5():
    _, res = matrix()
    pairs = res["pairs"]
    assert pairs and len(pairs) >= 4
    for p in pairs:
        assert contrast(p["fg"], p["bg"]) >= 4.5, p


def test_every_emitted_text_pair_is_authored_and_meets_4_5():
    mx, res = matrix()
    authored = {(p["fg"].lower(), p["bg"].lower()) for p in res["pairs"]}
    for (sc, w, h, st, t), o in mx.items():
        for x in o["text"]:
            assert "bg" in x, x
            assert contrast(x["fg"], x["bg"]) >= 4.5, (sc, st, x)
            assert (x["fg"].lower(), x["bg"].lower()) in authored, (sc, st, x)


def _median_lab(o):
    labs = []
    for p in pixels(o):
        L, C, H = oklch(p)
        labs.append((L, C * math.cos(math.radians(H)), C * math.sin(math.radians(H))))
    return [sorted(v[i] for v in labs)[len(labs) // 2] for i in range(3)]


def test_identity_separates_twenty_sessions_on_idle_tiles():
    # Fixture order: every session drawn as an idle M tile at the bg rung (the floor).
    sess = FX["sessions"]
    out = paint_many([req("M", 24, 2, "idle", s) for s in sess])["out"]
    meds = [_median_lab(o) for o in out]
    worst = min(math.dist(a, b) for i, a in enumerate(meds) for b in meds[i + 1:])
    assert worst >= 0.020, worst


def test_states_are_structurally_distinct_at_bg_rung():
    """Pattern = state: at 1×2 px/cell, each state's luminance structure differs from every other."""
    reqs = [req("M", 118, 2, st, _session(st)) for st in STATES]
    out = paint_many(reqs)["out"]
    sigs = []
    for o in out:
        Ls = [round(oklch(p)[0], 2) for p in pixels(o)]
        sigs.append(tuple(Ls))
    assert len(set(sigs)) == len(STATES)
