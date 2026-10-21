"""Behaviour contract for direction D (design/directions/d-dots/direction.mjs).

The module is imported by Node exactly as a host would and painted against the shared fixture.
Every assertion is about returned pixels/text, never the source text (CONTRACT §2, §5).
Adam 2026-10-15: "a set of coloured dots without any sophisticated background".
"""
import base64
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTION = ROOT / "design" / "directions" / "d-dots" / "direction.mjs"
TOKENS = ROOT / "packages" / "core" / "tokens.json"
FX = json.loads((ROOT / "tools" / "p1" / "stub-sessions.json").read_text())
STATES = FX["states"]
SIZES = {"XL": [(180, 120)], "M": [(118, 4), (118, 2), (22, 2)], "S": [(14, 2), (14, 1), (4, 2)]}

RUNNER = r"""
import { pathToFileURL } from 'node:url';
const [path, reqJson] = process.argv.slice(1);
const mod = await import(pathToFileURL(path).href);
const out = JSON.parse(reqJson).map(r => {
  const res = mod.paint(r);
  const px = res.pixels;
  return { len: px.length, b64: Buffer.from(px.buffer, px.byteOffset, px.length).toString('base64'), text: res.text };
});
process.stdout.write(JSON.stringify({ meta: mod.meta, out, pairs: mod.authoredPairs() }));
"""


def paint_many(reqs):
    r = subprocess.run(["node", "--input-type=module", "-e", RUNNER, str(DIRECTION), json.dumps(reqs)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def req(scale, w, h, state, session, t=0.0, reduced=False):
    return {"scale": scale, "w": w, "h": h, "state": state, "session": session, "t": t,
            "opts": {"reducedMotion": reduced, "depth": "truecolor"}}


def sess(state):
    return FX["degraded"] if state == "degraded" else next(s for s in FX["sessions"] if s["state"] == state)


def rgb(b64):
    raw = base64.b64decode(b64)
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 4)]


def lum(hexc):
    v = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    v = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def oklab(c):
    lin = [(x / 255 / 12.92) if x / 255 <= 0.04045 else ((x / 255 + 0.055) / 1.055) ** 2.4 for x in c]
    l = 0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]
    m = 0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]
    s = 0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]
    l, m, s = (v ** (1 / 3) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def test_only_working_animates_and_static_states_are_byte_identical():
    reqs, keys = [], []
    for scale, sizes in SIZES.items():
        for (w, h) in sizes:
            for st in STATES:
                for t in (0.0, 0.25, 0.5, 0.75):
                    reqs.append(req(scale, w, h, st, sess(st), t)); keys.append((scale, w, h, st))
    out = paint_many(reqs)["out"]
    frames = {}
    for k, o in zip(keys, out):
        assert o["len"] == k[1] * k[2] * 4
        frames.setdefault(k, set()).add(o["b64"])
    for (scale, w, h, st), f in frames.items():
        if st == "working":
            assert len(f) >= 3, f"working must move at {scale} {w}x{h}: {len(f)} distinct of 4"
        else:
            assert len(f) == 1, f"{st} must be static at {scale} {w}x{h}"


def test_reduced_motion_freezes_working():
    out = paint_many([req("M", 118, 4, "working", sess("working"), t, reduced=True) for t in (0, .25, .5, .75)])["out"]
    assert len({o["b64"] for o in out}) == 1


def test_plain_ground_every_pixel_is_ground_or_a_dot():
    # No sophisticated background: XL pixels are the one flat ground or belong to a dot (never a gradient field
    # underneath). The ground is the single most common colour of the working field and appears in every state.
    out = paint_many([req("XL", 180, 120, st, sess(st)) for st in STATES])["out"]
    grounds = []
    for o in out:
        px = rgb(o["b64"])
        counts = {}
        for c in px:
            counts[c] = counts.get(c, 0) + 1
        grounds.append(max(counts.items(), key=lambda kv: kv[1])[0])
    ground = grounds[STATES.index("working")]
    for st, o in zip(STATES, out):
        assert ground in set(rgb(o["b64"])), f"{st} has no plain ground between dots"
    assert len(set(g for g, st in zip(grounds, STATES) if st in ("working", "review", "unknown"))) == 1


def test_identity_hue_owns_small_idle_tiles():
    # The 16/20 grid is idle S tiles; the tile median must carry the identity hue, with neighbours separable.
    ss = FX["sessions"][:16]
    out = paint_many([req("S", 6, 2, "idle", s) for s in ss])["out"]
    labs = []
    for o in out:
        px = [oklab(c) for c in rgb(o["b64"])]
        labs.append(tuple(sorted(v[i] for v in px)[len(px) // 2] for i in range(3)))
    worst = min(math.dist(labs[i], labs[j]) for i in range(16) for j in range(i + 1, 16))
    assert worst >= 0.020, worst
    for lab in labs:
        h = math.degrees(math.atan2(lab[2], lab[1])) % 360
        assert 110 <= h < 340, h


def test_alarms_carry_literal_text_and_swatch_carries_none():
    out = paint_many([req("M", 118, 4, "needs-you", sess("needs-you")), req("M", 118, 4, "fault", sess("fault")),
                      req("S", 14, 2, "needs-you", sess("needs-you")), req("S", 14, 1, "fault", sess("fault")),
                      req("M", 118, 4, "unknown", sess("unknown")), req("XL", 180, 120, "fault", sess("fault"))]
                     + [req("S", 4, 2, st, sess(st)) for st in STATES])["out"]
    joined = ["".join(t["str"] for t in o["text"]) for o in out]
    assert "INPUT 4m" in joined[0] and "ERROR 2m" in joined[1]
    assert "INPUT 4m" in joined[2] and "ERROR 2m" in joined[3]
    assert "?" in joined[4] and "ERROR 2m" in joined[5]
    assert all(o["text"] == [] for o in out[6:])


def test_degraded_is_labelled_unbound_and_claims_no_hue():
    out = paint_many([req("XL", 180, 120, "unknown", FX["degraded"]), req("M", 118, 4, "unknown", FX["degraded"])])["out"]
    for o in out:
        assert any("unbound" in t["str"] for t in o["text"])
        for c in set(rgb(o["b64"])):
            _, a, b = oklab(c)
            assert math.hypot(a, b) < 0.03, c
    assert any("?" in t["str"] for t in out[0]["text"])


def test_states_differ_in_pattern_not_only_colour():
    # Structure carries state: the fraction of open (non-ground) dots differs between the calm and the alarm looks.
    out = paint_many([req("M", 118, 4, st, sess("idle")) for st in STATES])["out"]
    fills = []
    for o in out:
        px = rgb(o["b64"])
        ground = px.count(max(set(px), key=px.count))
        fills.append(1 - ground / len(px))
    assert len({round(f, 2) for f in fills}) >= 5, fills


def test_authored_pairs_meet_contrast_of_the_history_module_and_tokens_are_d2():
    # d-dots is kept as history (D2 locked 2026-10-21): its own contrast contract still holds, but packages/core/tokens.json
    # now belongs to D2 and is pinned by python/domain/dots.py + fixtures/dots-vectors.json, not by this module.
    res = paint_many([])
    for p in res["pairs"]:
        a, b = sorted((lum(p["fg"]), lum(p["bg"])), reverse=True)
        assert (a + 0.05) / (b + 0.05) >= 4.5, p
    tok = json.loads(TOKENS.read_text())
    assert tok["direction"] == "d2-scatter" and tok["ground"] is None
    assert set(tok["states"]) == {"idle", "thinking", "tool", "review", "needs-you", "fault", "unknown", "degraded"}
    assert tok["identity"]["hue_arc_deg"] == [110, 340]


def test_working_cloud_is_visible_beside_the_pill_label():
    # The TUI pill hides its left cells under the name plate; the cloud must still move in the uncovered cells.
    for (w, h) in [(14, 2), (14, 1), (22, 2)]:
        out = paint_many([req("S" if w < 20 else "M", w, h, "working", sess("working"), t) for t in (0, .25, .5, .75)])["out"]
        covered = max(t["x"] + len(t["str"]) for t in out[0]["text"])
        seen = set()
        for o in out:
            px = rgb(o["b64"])
            seen.add(tuple(px[y * w + x] for y in range(h) for x in range(covered, w)))
        assert len(seen) >= 3, (w, h, len(seen))
