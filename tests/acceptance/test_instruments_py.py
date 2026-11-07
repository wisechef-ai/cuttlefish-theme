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
