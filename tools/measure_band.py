"""Measure the palette cost of a band setting, from a clean process.

Usage: measure_band.py <centre> <width>
Writes band.py, then imports the package FRESH (separate process per setting —
an lru_cache or a stale import makes two settings report identical numbers,
which is how a band sweep silently measures the previous value).
"""
import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BAND = ROOT / "band.py"

MEASURE = r"""
import importlib.util, pathlib, sys
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "cuttlefish_theme", root / "__init__.py", submodule_search_locations=[str(root)])
m = importlib.util.module_from_spec(spec); m.__path__ = [str(root)]
sys.modules["cuttlefish_theme"] = m; spec.loader.exec_module(m)
from cuttlefish_theme.band import band, _BAND_CENTRE, _BAND_WIDTH
from cuttlefish_theme.chrome import _mantle_palette, _mantle_classes
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import contrast_ratio

colours = band()
ratios = [contrast_ratio("#E8E6EA", c) for c in colours]
families = {int(hex_to_oklch(c).h // 60) for c in colours}
sets, grounds = {}, []
for n in range(120):
    sid = f"s{n}"
    sets.setdefault(tuple(_mantle_classes(sid, "resting")), []).append(sid)
    grounds.append(hex_to_oklch(_mantle_palette(sid)).L)
print(f"{_BAND_CENTRE:.2f}/{_BAND_WIDTH:.2f} "
      f"colours={len(colours):2} families={len(families)} "
      f"swing={max(ratios)/min(ratios):.2f}x "
      f"groundL={min(grounds):.3f}-{max(grounds):.3f} "
      f"palettes={len(sets):3}/120 worst_collision={max(len(v) for v in sets.values()):2}")
"""


def measure(centre: str, width: str) -> None:
    source = BAND.read_text()
    source = re.sub(r"_BAND_CENTRE = [\d.]+", f"_BAND_CENTRE = {centre}", source)
    source = re.sub(r"_BAND_WIDTH = [\d.]+", f"_BAND_WIDTH = {width}", source)
    BAND.write_text(source)
    # A fresh interpreter per setting: same-process re-import returns the cached
    # module and reports the PREVIOUS band, which reads as "the knob does nothing".
    #
    # -B is load-bearing too. Python validates a .pyc by (mtime, size), both of
    # which are unchanged when a sweep rewrites `0.34` as `0.35` inside the same
    # second — so the subprocess silently executes the PREVIOUS setting's
    # bytecode. Measured: a 7-point sweep reported 3 duplicate rows and sent the
    # band tuning after a knob that appeared dead.
    subprocess.run([sys.executable, "-B", "-c", MEASURE, str(ROOT)], check=True)


if __name__ == "__main__":
    measure(sys.argv[1], sys.argv[2])
