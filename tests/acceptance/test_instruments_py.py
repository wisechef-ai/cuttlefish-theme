"""ACCEPTANCE CONTRACT PART — the Python instrument port is straight (locked; GREEN on its own, needs no product code).

(1) The same published / constructed reference values as desktop/test/acceptance/instruments.test.ts.
(2) A cross-check against the TS instruments themselves (run through node) on a deterministic dot set.
(3) The stdlib PNG reader and the pixel → organs detector: round trips on constructed pictures + rejection of bad input.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from . import instruments_py as ip
from .helpers import ROOT, STRICT

NODE_FALLBACK = "/home/adam/.hermes/tools/node-26.12.1-linux-x64/bin/node"


def close(a: float, b: float, eps: float, what: str) -> None:
    assert abs(a - b) <= eps, f"{what}: {a} vs {b} (±{eps})"


# ---- (1) reference values --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("hex_,L,a,b", [("#ffffff", 1.0, 0.0, 0.0), ("#000000", 0.0, 0.0, 0.0), ("#ff0000", 0.62796, 0.22486, 0.12585),
                                        ("#00ff00", 0.86644, -0.23389, 0.1795), ("#0000ff", 0.45201, -0.03246, -0.31153)])
def test_oklab_matches_ottosson_2020(hex_, L, a, b):
    lab = ip.rgb_to_oklab(ip.hex_to_rgb(hex_))
    close(lab[0], L, 2e-4, f"{hex_} L")
    close(lab[1], a, 2e-4, f"{hex_} a")
    close(lab[2], b, 2e-4, f"{hex_} b")


def test_mid_grey_is_about_0_6_not_0_5():
    close(ip.lch_of("#808080")[0], 0.5999, 5e-4, "#808080 L")


@pytest.mark.parametrize("bad", ["fff", "#fff", "#gggggg", "rgb(1,2,3)", ""])
def test_hex_to_rgb_rejects_malformed(bad):
    with pytest.raises(ValueError):
        ip.hex_to_rgb(bad)


def test_nearest_rank_percentile_wikipedia_example():
    xs = [15, 20, 35, 40, 50]
    assert [ip.percentile(xs, p) for p in (30, 40, 50, 100)] == [20, 20, 35, 50]
    assert ip.median([3, 1, 2, 10]) == 2.5
    with pytest.raises(ValueError):
        ip.percentile([], 50)


def test_compositing_and_delta_l():
    assert ip.composite((255, 255, 255), 0.5, (0, 0, 0)) == (127.5, 127.5, 127.5)
    opaque = ip.Dot(0, 0, 1, "#ffffff", 1)
    close(ip.dot_delta_l(opaque, "#000000"), 1, 1e-4, "white on black")
    close(ip.dot_delta_l(ip.Dot(0, 0, 1, "#ffffff", 0), "#000000"), 0, 1e-12, "transparent")


def test_hue_distance_wraps():
    assert (ip.hue_distance(350, 10), ip.hue_distance(10, 350), ip.hue_distance(90, 270)) == (20, 20, 180)


def grid(ink) -> list[ip.Dot]:
    return [ip.Dot(x, y, 3, "#ffffff", ink(x, y)) for y in range(12, 800, 24) for x in range(12, 1200, 24)]


def test_uniform_field_has_no_banding():
    assert all(a < 1e-9 for a in ip.band_spectrum(grid(lambda x, y: 0.2), "#000000", 1200, 800, 0))


def test_three_vertical_stripes_land_in_high_k_at_angle_0():
    b = ip.banding(grid(lambda x, y: 0.6 if math.floor(x / 1200 * 6) % 2 == 0 else 0.05), "#000000", 1200, 800)
    assert b["angle"] == 0 and 0.6 <= b["highK"] <= 1.0 and b["highK"] > 2 * b["lowK"], b


def test_one_smooth_horizontal_band_lands_in_low_k_at_angle_90():
    b = ip.banding(grid(lambda x, y: 0.1 + 0.5 * math.exp(-(((y - 400) / 100) ** 2))), "#000000", 1200, 800)
    assert b["angle"] == 90 and b["lowK"] > 0.5 and b["highK"] < 0.6 * b["lowK"], b


def test_spot_ratios_find_exactly_one_outlier():
    dots = grid(lambda x, y: 0.3) + [ip.Dot(600, 400, 18, "#ffffff", 0.5, "eyespot")]
    assert ip.spot_ratios(dots) == {"first": 6, "second": 1}


def test_coverage_lightness_stats_organ_key():
    dots = grid(lambda x, y: 1)
    close(ip.coverage(dots, 1200, 800), len(dots) * math.pi * 9 / (1200 * 800), 1e-12, "coverage")
    st = ip.lightness_stats(dots, "#000000")
    close(st["mean"], 1, 1e-4, "mean ΔL")
    assert st["n"] == len(dots)
    moved = [ip.Dot(d.x, d.y, d.r, d.color, 0.1) for d in dots]
    assert ip.organ_key(moved) == ip.organ_key(dots)
    assert ip.organ_key([ip.Dot(13, dots[0].y, 3, "#ffffff", 1)] + dots[1:]) != ip.organ_key(dots)


# ---- (2) the TS instruments agree --------------------------------------------------------------------------------------

def _node() -> str | None:
    found = os.environ.get("CF_NODE") or shutil.which("node") or (NODE_FALLBACK if Path(NODE_FALLBACK).is_file() else None)
    if found is None and STRICT:
        pytest.fail("node is needed to cross-check the instruments")
    return found


def _scatter(n: int) -> list[dict]:
    s, out = 12345, []
    for _ in range(n):
        vals = []
        for _k in range(6):
            s = (s * 1103515245 + 12345) % 2**31
            vals.append(s / 2**31)
        x, y, r, a, c1, c2 = vals
        out.append({"x": 1200 * x, "y": 800 * y, "r": 2 + 8 * r, "alpha": round(0.05 + 0.5 * a, 3),
                    "color": f"#{int(255 * c1):02x}{int(255 * c2):02x}{int(255 * x):02x}", "role": "organ"})
    out[3]["r"] = 40
    out[4]["alpha"] = 0
    return out


JS = """
import { readFileSync } from 'node:fs'
import { banding, coverage, lightnessStats, meanChroma, spotRatios } from %r
const { dots, ground } = JSON.parse(readFileSync(process.argv[1], 'utf8'))
process.stdout.write(JSON.stringify({ stats: lightnessStats(dots, ground), band: banding(dots, ground, 1200, 800),
  spot: spotRatios(dots), cov: coverage(dots, 1200, 800), chroma: meanChroma(dots) }))
"""


@pytest.mark.parametrize("ground", ["#141416", "#2e3440", "#fbfbfa"])
def test_python_port_equals_the_ts_instruments(tmp_path, ground):
    node = _node()
    if node is None:
        pytest.skip("node not available")
    raw = _scatter(300)
    f = tmp_path / "dots.json"
    f.write_text(json.dumps({"dots": raw, "ground": ground}))
    inst = ROOT / "desktop" / "test" / "acceptance" / "instruments.ts"
    out = subprocess.run([node, "--input-type=module", "-e", JS % inst.as_uri(), str(f)], capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    dots = [ip.Dot(**d) for d in raw]
    st, b, sp = ip.lightness_stats(dots, ground), ip.banding(dots, ground, 1200, 800), ip.spot_ratios(dots)
    close(st["mean"], js["stats"]["mean"], 1e-9, "mean")
    close(st["p95"], js["stats"]["p95"], 1e-9, "p95")
    assert st["n"] == js["stats"]["n"]
    close(b["lowK"], js["band"]["lowK"], 1e-9, "lowK")
    close(b["highK"], js["band"]["highK"], 1e-9, "highK")
    assert b["angle"] == js["band"]["angle"]
    close(sp["first"], js["spot"]["first"], 1e-9, "spot first")
    close(sp["second"], js["spot"]["second"], 1e-9, "spot second")
    close(ip.coverage(dots, 1200, 800), js["cov"], 1e-12, "coverage")
    close(ip.mean_chroma(dots), js["chroma"], 1e-9, "chroma")


# ---- (3) PNG reader + pixel detector ----------------------------------------------------------------------------------

def picture(w, h, ground, discs):
    """discs: (cx, cy, r, colour). Flat, un-antialiased discs on a flat ground."""
    gr = ip.hex_to_rgb(ground)
    rows = []
    for y in range(h):
        row = bytearray(bytes(gr) * w)
        for cx, cy, r, col in discs:
            if abs(y - cy) > r + 1:
                continue
            rgb = ip.hex_to_rgb(col)
            for x in range(max(0, int(cx - r) - 1), min(w, int(cx + r) + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    row[3 * x:3 * x + 3] = bytes(rgb)
        rows.append(bytes(row))
    return rows


def test_png_round_trip_and_unfiltering(tmp_path):
    rows = [bytes((x * 7 + y) % 256 for x in range(3 * 9)) for y in range(5)]
    p = tmp_path / "a.png"
    ip.write_png(p, 9, 5, rows)
    img = ip.read_png(p)
    assert (img.width, img.height) == (9, 5) and img.rows == rows
    assert img.pixel(2, 1) == tuple(rows[1][6:9])


def _png_with(tmp_path, ihdr, rows_raw):
    import struct
    import zlib

    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xFFFFFFFF)
    p = tmp_path / "x.png"
    p.write_bytes(ip.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", *ihdr)) + chunk(b"IDAT", zlib.compress(rows_raw))
                  + chunk(b"IEND", b""))
    return p


def test_png_filters_sub_up_average_paeth_and_rgba_and_gray(tmp_path):
    # 3×2 RGB, row 0 filter Sub, row 1 filter Paeth: bytes chosen so that the expected pixels are known
    row0 = bytes([10, 20, 30, 1, 1, 1, 1, 1, 1])                       # Sub: 10,20,30 | 11,21,31 | 12,22,32
    row1 = bytes([1, 1, 1, 0, 0, 0, 0, 0, 0])                          # Paeth on top of row0
    img = ip.read_png(_png_with(tmp_path, (3, 2, 8, 2, 0, 0, 0), b"\x01" + row0 + b"\x04" + row1))
    assert img.rows[0] == bytes([10, 20, 30, 11, 21, 31, 12, 22, 32])
    assert img.rows[1][:3] == bytes([11, 21, 31])
    rgba = ip.read_png(_png_with(tmp_path, (2, 1, 8, 6, 0, 0, 0), b"\x00" + bytes([1, 2, 3, 255, 4, 5, 6, 128])))
    assert rgba.rows[0] == bytes([1, 2, 3, 4, 5, 6])
    gray = ip.read_png(_png_with(tmp_path, (2, 1, 8, 0, 0, 0, 0), b"\x00" + bytes([9, 200])))
    assert gray.rows[0] == bytes([9, 9, 9, 200, 200, 200])


def test_png_reader_rejects_what_it_cannot_read(tmp_path):
    (tmp_path / "junk.png").write_bytes(b"not a png at all")
    with pytest.raises(ip.PngError):
        ip.read_png(tmp_path / "junk.png")
    with pytest.raises(ip.PngError, match="unsupported"):
        ip.read_png(_png_with(tmp_path, (2, 1, 16, 2, 0, 0, 0), b"\x00" * 13))        # 16-bit
    with pytest.raises(ip.PngError, match="unsupported"):
        ip.read_png(_png_with(tmp_path, (2, 1, 8, 2, 0, 0, 1), b"\x00" * 7))          # interlaced
    with pytest.raises(ip.PngError, match="wrong length"):
        ip.read_png(_png_with(tmp_path, (2, 2, 8, 2, 0, 0, 0), b"\x00" * 7))          # short data
    good = tmp_path / "g.png"
    ip.write_png(good, 4, 4, [bytes(12)] * 4)
    good.write_bytes(good.read_bytes()[:-20])
    with pytest.raises(ip.PngError):
        ip.read_png(good)


def test_detector_finds_the_constructed_organs(tmp_path):
    discs = [(100 + 90 * i, 120 + 60 * (i % 3), 9 + (i % 3), "#2a2a30" if i % 2 else "#222228") for i in range(8)]
    rows = picture(900, 400, "#141416", discs)
    img = ip.Image(900, 400, rows)
    dots, ground = ip.detect_organs(img, (0, 0, 900, 400))
    assert ground == "#141416" and len(dots) == 8
    for d, (cx, cy, r, _c) in zip(dots, discs, strict=True):
        assert abs(d.x - cx) < 1 and abs(d.y - cy) < 1 and abs(d.r - r) < 1.5
    m = ip.field_metrics(img, (0, 0, 900, 400))
    want = [ip.dot_delta_l(ip.Dot(0, 0, 1, c, 1), "#141416") for *_xy, c in discs]
    assert m["organs_detected"] == 8 and m["p95_dL"] >= m["mean_dL"]
    close(m["mean_dL"], sum(want) / 8, 1e-3, "mean ΔL equals the constructed discs' ΔL")
    close(m["p95_dL"], max(want), 1e-3, "p95 ΔL of 8 discs is the largest")


def test_detector_honours_region_and_exclusions_and_ignores_specks():
    img = ip.Image(300, 200, picture(300, 200, "#fbfbfa", [(50, 50, 8, "#e8e8e6"), (200, 100, 8, "#e8e8e6"), (150, 20, 0.5, "#e8e8e6")]))
    assert len(ip.detect_organs(img, (0, 0, 300, 200))[0]) == 2, "a 1-px speck (< MIN_AREA) is not an organ"
    assert len(ip.detect_organs(img, (100, 0, 200, 200))[0]) == 1, "the region crops"
    assert len(ip.detect_organs(img, (0, 0, 300, 200), exclude=[(0, 0, 100, 100)])[0]) == 1, "exclusions are ignored pixels"
    assert ip.detect_organs(img, (100, 0, 200, 200))[0][0].x == pytest.approx(100, abs=1), "coordinates are region-relative"


def test_detector_rejects_a_bad_region_and_a_fully_excluded_one():
    img = ip.Image(10, 10, [bytes(30)] * 10)
    for region in ((0, 0, 11, 10), (-1, 0, 5, 5), (0, 0, 0, 5)):
        with pytest.raises(ValueError, match="outside"):
            ip.detect_organs(img, region)
    with pytest.raises(ValueError, match="excluded"):
        ip.detect_organs(img, (0, 0, 10, 10), exclude=[(0, 0, 10, 10)])


def test_stripes_in_pixels_read_as_high_k_and_a_smooth_band_as_low_k():
    stripes = [(x, y, 5, "#34343c" if math.floor(x / 1200 * 6) % 2 == 0 else "#18181b")
               for x in range(20, 1200, 40) for y in range(20, 800, 40)]
    m = ip.field_metrics(ip.Image(1200, 800, picture(1200, 800, "#141416", stripes)), (0, 0, 1200, 800))
    assert m["organs_detected"] == 600 and m["highK"] >= 0.6 and m["highK"] > 2 * m["lowK"], m
    band = [(x, y, 5, "#34343c" if abs(y - 400) < 120 else "#18181b") for x in range(20, 1200, 40) for y in range(20, 800, 40)]
    m = ip.field_metrics(ip.Image(1200, 800, picture(1200, 800, "#141416", band)), (0, 0, 1200, 800))
    assert m["lowK"] >= 0.55 and m["highK"] <= 0.6 * m["lowK"], m


# ---- (4) boundaries: every rule pinned at its edge (mutation-tested; see contract/PARTS.md) ---------------------------------

def test_rgb_to_hex_clamps_and_rounds():
    assert ip.rgb_to_hex((-5, 300, 128.4)) == "#00ff80"
    assert ip.rgb_to_hex((0, 255, 1.6)) == "#00ff02"


def test_composite_clamps_alpha_and_requires_equal_lengths():
    assert ip.composite((10, 20, 30), 2.0, (0, 0, 0)) == (10, 20, 30)
    assert ip.composite((10, 20, 30), -1.0, (1, 2, 3)) == (1, 2, 3)
    with pytest.raises(ValueError):
        ip.composite((1, 2), 0.5, (1, 2, 3))


def test_percentile_edges_and_empty_samples():
    xs = [3, 1, 2]
    assert ip.percentile(xs, 0) == 1 and ip.percentile(xs, 0.0001) == 1 and ip.percentile(xs, 100) == 3
    assert ip.percentile(xs, 66.7) == 3 and ip.percentile(xs, 66.6) == 2
    for fn in (ip.mean, ip.median):
        with pytest.raises(ValueError):
            fn([])


def test_visible_needs_both_alpha_and_radius():
    dots = [ip.Dot(0, 0, 0, "#ffffff", 1), ip.Dot(0, 0, 1, "#ffffff", 0), ip.Dot(0, 0, 1e-9, "#ffffff", 1e-9),
            ip.Dot(0, 0, 2, "#ffffff", 1)]
    assert [(d.r, d.alpha) for d in ip.visible(dots)] == [(1e-9, 1e-9), (2, 1)]
    assert ip.lightness_stats([], "#000000") == {"mean": 0.0, "p95": 0.0, "n": 0}
    assert ip.lightness_stats(dots[:2], "#000000")["n"] == 0
    assert ip.mean_chroma([]) == 0.0 and ip.mean_chroma(dots[:2]) == 0.0
    close(ip.mean_chroma([ip.Dot(0, 0, 1, "#ff0000", 1)]), 0.25768, 1e-4, "chroma of pure red")
    close(ip.lch_of("#ff0000")[2], 29.23, 0.01, "hue of pure red")


def test_spot_ratios_with_one_dot_and_none():
    assert ip.spot_ratios([]) == {"first": 0.0, "second": 0.0}
    assert ip.spot_ratios([ip.Dot(0, 0, 3, "#ffffff", 1)]) == {"first": 1.0, "second": 0.0}
    assert ip.spot_ratios([ip.Dot(0, 0, 3, "#ffffff", 1), ip.Dot(1, 1, 6, "#ffffff", 1, "eyespot")]) == {"first": 2.0, "second": 1.0}


def test_band_spectrum_edges():
    assert ip.band_spectrum([], "#000000", 1200, 800, 0) == [0.0] * 7, "no organs, no spectrum"
    only_eye = [ip.Dot(10, 10, 3, "#ffffff", 1, "eyespot")]
    assert ip.band_spectrum(only_eye, "#000000", 1200, 800, 0) == [0.0] * 7, "eye-spots are not organs"
    assert len(ip.band_spectrum(grid(lambda x, y: 0.2), "#000000", 1200, 800, 45, bins=32)) == 15
    invisible = [ip.Dot(10, 10, 3, "#ffffff", 0)]
    assert ip.band_spectrum(invisible, "#000000", 1200, 800, 0) == [0.0] * 7, "a closed organ inks nothing"
    diag = grid(lambda x, y: 0.1 + 0.5 * math.exp(-(((x + y - 1000) / 150) ** 2)))
    assert ip.banding(diag, "#000000", 1200, 800)["angle"] == 45
    anti = grid(lambda x, y: 0.1 + 0.5 * math.exp(-(((x - y - 100) / 150) ** 2)))
    assert ip.banding(anti, "#000000", 1200, 800)["angle"] == 135


def test_a_dot_exactly_on_the_far_edge_lands_in_the_last_bin_and_one_before_the_origin_in_the_first():
    on_edge = [ip.Dot(1200, 400, 3, "#ffffff", 1), ip.Dot(0, 400, 3, "#ffffff", 0.1)]
    s = ip.band_spectrum(on_edge, "#000000", 1200, 800, 0)
    assert s[0] > 0, "both end bins are populated (clamped), so the profile is not flat"
    below = [ip.Dot(-50, 400, 3, "#ffffff", 1), ip.Dot(600, 400, 3, "#ffffff", 0.1)]
    assert max(ip.band_spectrum(below, "#000000", 1200, 800, 0)) > 0


def reference_paeth(a, b, c):
    """The PNG spec's Paeth predictor, written independently of the code under test."""
    candidates = [(abs(b - c), 0, a), (abs(a - c), 1, b), (abs(a + b - 2 * c), 2, c)]   # |p−a|, |p−b|, |p−c|; ties prefer a, b, c
    return min(candidates)[2]


def png_filtered(tmp_path, ctype, width, height):
    """Encode an image with every filter type (cycling per row) by the PNG spec's forward filters; return (path, expected rgb rows)."""
    import struct
    import zlib
    chans = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    stride = width * chans
    raw = [bytes((7 * x + 13 * y + (x * y) % 11) % 256 for x in range(stride)) for y in range(height)]
    out, prev = bytearray(), bytes(stride)
    for y, row in enumerate(raw):
        kind = y % 5
        line = bytearray()
        for i in range(stride):
            a = row[i - chans] if i >= chans else 0
            b = prev[i]
            c = prev[i - chans] if i >= chans else 0
            pred = (0, a, b, (a + b) // 2, reference_paeth(a, b, c))[kind]
            line.append((row[i] - pred) & 255)
        out += bytes([kind]) + line
        prev = row

    def chunk(k, body):
        return struct.pack(">I", len(body)) + k + body + struct.pack(">I", zlib.crc32(k + body) & 0xFFFFFFFF)
    p = tmp_path / f"f{ctype}.png"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, ctype, 0, 0, 0)
    p.write_bytes(ip.PNG_SIG + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b""))
    rgb = []
    for row in raw:
        px = bytearray()
        for x in range(width):
            px += bytes((row[x * chans],) * 3) if ctype in (0, 4) else row[x * chans:x * chans + 3]
        rgb.append(bytes(px))
    return p, rgb


@pytest.mark.parametrize("ctype", [0, 2, 4, 6])
def test_every_png_filter_type_and_colour_type_round_trips(tmp_path, ctype):
    p, rgb = png_filtered(tmp_path, ctype, 7, 10)
    img = ip.read_png(p)
    assert (img.width, img.height) == (7, 10) and img.rows == rgb


def test_png_rejects_zero_sized_and_unknown_colour_types_and_missing_ihdr(tmp_path):
    import struct
    import zlib
    for ihdr in ((0, 1, 8, 2, 0, 0, 0), (1, 0, 8, 2, 0, 0, 0), (1, 1, 8, 3, 0, 0, 0)):
        body = struct.pack(">IIBBBBB", *ihdr)
        p = tmp_path / "z.png"
        crc = struct.pack(">I", zlib.crc32(b"IHDR" + body) & 0xFFFFFFFF)
        p.write_bytes(ip.PNG_SIG + struct.pack(">I", len(body)) + b"IHDR" + body + crc)
        with pytest.raises(ip.PngError, match="unsupported"):
            ip.read_png(p)
    p = tmp_path / "n.png"
    p.write_bytes(ip.PNG_SIG)
    with pytest.raises(ip.PngError, match="no IHDR"):
        ip.read_png(p)
    p.write_bytes(ip.PNG_SIG + struct.pack(">I", 99) + b"IHDR" + b"\x00" * 3)
    with pytest.raises(ip.PngError, match="truncated"):
        ip.read_png(p)


def blocks(w, h, ground, items):
    """items: (x, y, bw, bh, colour) solid rectangles."""
    rows = [bytearray(bytes(ip.hex_to_rgb(ground)) * w) for _ in range(h)]
    for x, y, bw, bh, col in items:
        for yy in range(y, y + bh):
            rows[yy][3 * x:3 * (x + bw)] = bytes(ip.hex_to_rgb(col)) * bw
    return ip.Image(w, h, [bytes(r) for r in rows])


def test_detector_area_limits_connectivity_and_colours():
    g = "#141416"
    img = blocks(400, 300, g, [(10, 10, 2, 2, "#303030"), (30, 10, 3, 1, "#303030"), (50, 10, 1, 4, "#202020"),
                               (100, 10, 50, 100, "#303030"), (200, 10, 51, 98, "#303030"),
                               (300, 200, 2, 2, "#303030"), (302, 202, 2, 2, "#303030")])
    dots, ground = ip.detect_organs(img, (0, 0, 400, 300))
    got = [(round(d.x, 2), round(d.y, 2), d.color) for d in dots]
    assert ground == g
    assert (10.5, 10.5, "#303030") in got, "a 2×2 block (area 4 = MIN_AREA) is an organ"
    assert all(abs(x - 31) > 0.1 for x, _y, _c in got), "3 px is below MIN_AREA"
    assert (50.0, 11.5, "#202020") in got, "a 1×4 bar has area 4"
    assert (124.5, 59.5, "#303030") in got, "area 5000 = MAX_AREA is an organ, centroid exact"
    assert (225.0, 58.5, "#303030") in got, "a 51×98 block (area 4998 < MAX_AREA) is an organ"
    assert len([1 for x, y, _c in got if x > 290]) == 2, "diagonally touching blocks are two components (4-connectivity)"


def test_detector_area_limit_is_inclusive_at_5000_and_exclusive_at_5001():
    g = "#141416"
    img = blocks(300, 200, g, [(10, 10, 100, 50, "#303030"), (150, 10, 101, 50, "#303030")])
    assert len(ip.detect_organs(img, (0, 0, 300, 200))[0]) == 1
    assert ip.detect_organs(img, (0, 0, 300, 200))[0][0].x == pytest.approx(59.5)


def test_detector_ink_threshold_edge_and_ground_is_the_mode():
    base = ip.rgb_to_oklab((20, 20, 22))[0]
    levels = {v: abs(ip.rgb_to_oklab((v, v, v))[0] - base) for v in range(18, 40)}
    below = max(v for v, d in levels.items() if v > 20 and d < ip.INK_THRESHOLD)
    above = min(v for v, d in levels.items() if v > 20 and d >= ip.INK_THRESHOLD)
    assert above == below + 1
    img = blocks(60, 20, "#141416", [(5, 5, 4, 4, ip.rgb_to_hex((below,) * 3)), (20, 5, 4, 4, ip.rgb_to_hex((above,) * 3))])
    dots, _ = ip.detect_organs(img, (0, 0, 60, 20))
    assert [round(d.x) for d in dots] == [22], "ΔL just under the threshold is ground; at the threshold it is ink"
    most = blocks(60, 20, "#141416", [(0, 0, 40, 20, "#303030"), (50, 5, 4, 4, "#141416")])
    assert ip.detect_organs(most, (0, 0, 60, 20))[1] == "#303030", "the ground is the MOST frequent colour, not the corner or the first"
    tie = blocks(2, 1, "#141416", [(1, 0, 1, 1, "#303030")])
    assert ip.detect_organs(tie, (0, 0, 2, 1))[1] in ("#141416", "#303030")


def test_detector_exclusions_are_ignored_and_do_not_count_toward_the_ground():
    img = blocks(100, 50, "#141416", [(0, 0, 100, 25, "#303030"), (60, 30, 4, 4, "#303030")])
    dots, ground = ip.detect_organs(img, (0, 0, 100, 50), exclude=[(0, 0, 100, 25)])
    assert ground == "#141416" and len(dots) == 1
    inner = blocks(100, 50, "#141416", [(10, 10, 6, 6, "#303030")])
    assert len(ip.detect_organs(inner, (0, 0, 100, 50), exclude=[(13, 10, 6, 6)])[0]) == 1, "part of an organ is still an organ"
    pinhole = ip.detect_organs(inner, (0, 0, 100, 50), exclude=[(10, 10, 1, 1)])[0][0]
    assert pinhole.x == pytest.approx(440 / 35, abs=1e-6), "the excluded pixel is gone"
    assert len(ip.detect_organs(inner, (0, 0, 100, 50), exclude=[(11, 11, 6, 6)])[0]) == 1
    assert ip._inside(5, 5, [(5, 5, 1, 1)]) and not ip._inside(6, 5, [(5, 5, 1, 1)]) and not ip._inside(5, 6, [(5, 5, 1, 1)])
    assert not ip._inside(4, 5, [(5, 5, 1, 1)]) and not ip._inside(5, 4, [(5, 5, 1, 1)])


def test_field_metrics_with_no_organs_is_all_zero():
    zero = {"organs_detected": 0, "p95_dL": 0.0, "mean_dL": 0.0, "lowK": 0.0, "highK": 0.0}
    assert ip.field_metrics(blocks(20, 20, "#141416", []), (0, 0, 20, 20)) == zero


def test_image_pixel_indexes_x_then_y():
    img = ip.Image(2, 2, [bytes([1, 2, 3, 4, 5, 6]), bytes([7, 8, 9, 10, 11, 12])])
    assert img.pixel(1, 0) == (4, 5, 6) and img.pixel(0, 1) == (7, 8, 9)
    assert ip.organ_key([ip.Dot(1, 2, 1, "#000000", 1, "eyespot"), ip.Dot(3.456, 4, 1, "#000000", 1)]) == "3.46,4.00"


# ---- (5) the remaining edges --------------------------------------------------------------------------------------------

def test_paeth_equals_the_spec_predictor_everywhere():
    for a in range(0, 14):
        for b in range(0, 14):
            for c in range(0, 14):
                assert ip._paeth(a, b, c) == reference_paeth(a, b, c), (a, b, c)


def test_png_with_enough_pixels_to_exercise_every_neighbour(tmp_path):
    p, rgb = png_filtered(tmp_path, 6, 23, 31)
    assert ip.read_png(p).rows == rgb


def test_png_one_pixel_is_valid_and_bad_methods_are_refused(tmp_path):
    import struct
    import zlib

    def png(ihdr, raw):
        def chunk(k, b):
            return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xFFFFFFFF)
        f = tmp_path / "one.png"
        head = chunk(b"IHDR", struct.pack(">IIBBBBB", *ihdr))
        f.write_bytes(ip.PNG_SIG + head + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        return f
    assert ip.read_png(png((1, 1, 8, 2, 0, 0, 0), b"\x00\x01\x02\x03")).rows == [bytes([1, 2, 3])]
    assert ip.read_png(png((1, 2, 8, 2, 0, 0, 0), b"\x00\x01\x02\x03\x00\x04\x05\x06")).rows == [bytes([1, 2, 3]), bytes([4, 5, 6])]
    for ihdr in ((1, 1, 8, 2, 1, 0, 0), (1, 1, 8, 2, 0, 1, 0), (1, 1, 8, 2, 0, 0, 2)):
        with pytest.raises(ip.PngError, match="unsupported"):
            ip.read_png(png(ihdr, b"\x00\x01\x02\x03"))
    out = tmp_path / "w.png"
    ip.write_png(out, 2, 1, [bytes([9, 8, 7, 6, 5, 4])])
    raw = out.read_bytes()
    assert raw[24:29] == bytes([8, 2, 0, 0, 0]), "write_png declares 8-bit RGB, deflate, adaptive filtering, no interlace"
    assert ip.read_png(out).rows == [bytes([9, 8, 7, 6, 5, 4])]


def test_banding_of_a_flat_or_empty_field_is_zero_at_angle_zero_and_closed_organs_ink_nothing():
    assert ip.banding([], "#000000", 1200, 800) == {"lowK": 0.0, "highK": 0.0, "angle": 0}
    assert ip.banding(grid(lambda x, y: 0), "#000000", 1200, 800) == {"lowK": 0.0, "highK": 0.0, "angle": 0}
    flat = [ip.Dot(100, 100, 3, "#ffffff", 0.5), ip.Dot(700, 100, 3, "#ffffff", 0.5)]
    with_closed = flat + [ip.Dot(1100, 100, 0, "#ffffff", 1.0)]
    closed = ip.band_spectrum(with_closed, "#000000", 1200, 800, 0)
    assert closed != ip.band_spectrum(flat, "#000000", 1200, 800, 0) and max(closed) > 0.2, "a zero-radius organ inks 0, it does not vanish"
    twin = flat + [ip.Dot(1100, 100, 3, "#ffffff", 0.5)]
    assert max(ip.band_spectrum(twin, "#000000", 1200, 800, 0)) < 1e-9, "three equally inked organs are flat"


def test_detector_uses_all_three_channels_of_a_coloured_ground():
    img = blocks(40, 20, "#102030", [(5, 5, 4, 4, "#304050"), (20, 5, 4, 4, "#10a030")])
    dots, ground = ip.detect_organs(img, (0, 0, 40, 20))
    assert ground == "#102030" and [d.color for d in dots] == ["#304050", "#10a030"]


def test_detector_connects_in_all_four_directions():
    g = "#141416"
    stairs = [(20 - i, 2 * i + j, 1, 1, "#303030") for i in range(8) for j in (0, 1)]
    stairs += [(19 - i, 2 * i + 1, 1, 1, "#303030") for i in range(8)]
    img = blocks(40, 40, g, stairs)
    dots = ip.detect_organs(img, (0, 0, 40, 40))[0]
    assert len(dots) == 1, "a down-left staircase is ONE component (needs left and down moves)"
    ush = [(5, y, 1, 1, "#303030") for y in range(5, 20)] + [(x, 19, 1, 1, "#303030") for x in range(5, 20)]
    ush += [(19, y, 1, 1, "#303030") for y in range(3, 20)]
    assert len(ip.detect_organs(blocks(40, 40, g, ush), (0, 0, 40, 40))[0]) == 1, "a U needs right and up moves"
    gap = [(5, y, 1, 1, "#303030") for y in range(5, 15)] + [(7, y, 1, 1, "#303030") for y in range(5, 15)]
    assert len(ip.detect_organs(blocks(40, 40, g, gap), (0, 0, 40, 40))[0]) == 2, "a one-pixel gap separates two organs"
    assert len(ip.detect_organs(blocks(40, 40, g, [(5, 5, 1, 10, "#303030"), (6, 5, 1, 1, "#303030")]), (0, 0, 40, 40))[0]) == 1


def test_detector_accepts_regions_that_touch_the_image_edges():
    img = blocks(30, 20, "#141416", [(29, 19, 1, 1, "#303030"), (0, 0, 2, 2, "#303030")])
    assert len(ip.detect_organs(img, (0, 0, 30, 20))[0]) == 1, "the whole image is a valid region"
    assert ip.detect_organs(img, (0, 0, 1, 1))[1] == "#303030", "a 1×1 region at the origin is valid"
    assert ip.detect_organs(img, (29, 19, 1, 1))[1] == "#303030", "a 1×1 region in the last pixel is valid"
    assert ip.detect_organs(img, (28, 18, 2, 2))[0] == [], "a 1-px speck is below MIN_AREA"


def test_field_metrics_and_dot_geometry_on_a_small_known_picture():
    g = "#141416"
    img = blocks(60, 40, g, [(10, 10, 4, 4, "#303030"), (30, 10, 6, 6, "#202022")])
    dots, _ = ip.detect_organs(img, (5, 5, 50, 30))
    assert [(d.x, d.y) for d in dots] == [(6.5, 6.5), (27.5, 7.5)], "centroids are relative to the region"
    assert dots[0].r == pytest.approx(math.sqrt(16 / math.pi)) and dots[1].r == pytest.approx(math.sqrt(36 / math.pi))
    m = ip.field_metrics(img, (5, 5, 50, 30))
    d1, d2 = (ip.dot_delta_l(d, g) for d in dots)
    assert m["organs_detected"] == 2 and m["mean_dL"] == pytest.approx((d1 + d2) / 2) and m["p95_dL"] == pytest.approx(max(d1, d2))
