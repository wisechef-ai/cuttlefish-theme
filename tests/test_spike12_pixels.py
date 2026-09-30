"""Behaviour of the spike-12 pixel checks on synthetic screenshots (no terminal needed)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL.Image")
HERE = Path(__file__).resolve().parents[1] / "tools" / "spikes" / "12-terminal-rendering-real-tui"
sys.path.insert(0, str(HERE))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mp = _load("mantle_pixels")
cf = _load("classify_fringe")

A, B, C, D = (18, 18, 18), (58, 58, 58), (98, 98, 98), (0, 255, 255)
PAL = {A, B, C, D}
BG = (250, 250, 250)


def band(tmp_path, stripe_colors, seam_row=None, blend_row=None, w=200, cell_h=10):
    """4 half-cell stripes of width w on a light background, like 2 rows of ▀."""
    img = PIL.new("RGB", (w + 20, 4 * cell_h + 40), BG)
    px = img.load()
    for i, col in enumerate(stripe_colors):
        for y in range(20 + i * cell_h, 20 + (i + 1) * cell_h):
            for x in range(10, 10 + w):
                px[x, y] = col
    if seam_row is not None:          # background shows through: a font glyph that does not fill
        for x in range(10, 10 + w):
            px[x, 20 + seam_row] = BG
    if blend_row is not None:         # anti-aliased split between two stripes
        a, b = stripe_colors[blend_row // cell_h - 1], stripe_colors[blend_row // cell_h]
        for x in range(10, 10 + w):
            px[x, 20 + blend_row] = tuple((p + q) // 2 for p, q in zip(a, b))
    f = tmp_path / "shot.png"
    img.save(f)
    return f


def test_seamless_band_passes(tmp_path):
    m = mp.measure(band(tmp_path, [A, B, C, D]), PAL)
    assert m["found"] and m["off_palette_px"] == 0 and m["contiguous"] and m["stripes"] == 4


def test_background_seam_is_a_gap(tmp_path):
    f = band(tmp_path, [A, B, C, D], seam_row=10)
    r = cf.classify(f, PAL)
    assert r["gap"] > 0
    assert mp.measure(f, PAL)["contiguous"] is False


def test_antialiased_split_is_a_blend_not_a_gap(tmp_path):
    r = cf.classify(band(tmp_path, [A, D, A, D], blend_row=10), PAL)
    assert r["blend"] == 200 and r["gap"] == 0


def test_no_band_is_reported(tmp_path):
    img = PIL.new("RGB", (50, 50), BG)
    f = tmp_path / "blank.png"
    img.save(f)
    assert mp.measure(f, PAL) == {"found": False}
