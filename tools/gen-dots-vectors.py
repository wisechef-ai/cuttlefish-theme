#!/usr/bin/env python3
"""Golden vectors for the D2 scatter grammar: python/domain/dots.py (the oracle) -> packages/core/fixtures/dots-vectors.json.

    python3 tools/gen-dots-vectors.py            # (re)write the fixture
    python3 tools/gen-dots-vectors.py --check    # CI: exit 1 if the committed fixture is not what the oracle writes

packages/core/test/dots.parity.test.ts asserts EXACT glyph + rgb per organ against this file.
Deterministic: no clock, no randomness; output is byte-stable.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages" / "core" / "fixtures" / "dots-vectors.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"cf_{name}", ROOT / "python" / "domain" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


dots, allocator = _load("dots"), _load("allocator")

SEEDS = ["20261015_232342_2c978c", "sess-b", "sess-c", "ledger/lineage-4"]   # >= 3 sessions
STATES = list(dots.STATES) + ["degraded"]
OFFSETS = [0.0, 0.05, 0.2, 0.45, 0.8, 1.3, 2.0, 3.0, 4.2, 5.7, 7.5]          # several values of t
ENTERED = [0.0, 1000.0]
# (scale, cols, rows, density) variants beyond the default dims: per_tick, thinning and noise scale with the grid.
ALT_DIMS = [("XL", 96, 32, 0.10), ("M", 40, 2, 0.10), ("S", 6, 3, 0.5)]


def scenes() -> list[dict]:
    out: list[dict] = []

    def add(seed, scale, cols, rows, dens, entered, state, twinkle=True):
        # Identity comes from the existing 20-slot allocator (no peers): the vector pins the hue it picked.
        hue = None if state == "degraded" else allocator.allocate(seed, []).hue_deg
        times = [entered + o for o in OFFSETS]
        for t, cells in zip(times, dots.render(seed, hue, state, cols, rows, entered, times, dens, twinkle)):
            out.append({"seed": seed, "hue": hue, "state": state, "scale": scale, "cols": cols, "rows": rows,
                        "density": dens, "twinkle": twinkle, "entered": entered, "t": t,
                        "cells": [[x, y, g, *rgb, pig] for x, y, g, rgb, pig in cells]})

    for seed in SEEDS:
        for scale, (cols, rows, dens) in dots.SCALES.items():
            for entered in ENTERED:
                for state in STATES:
                    add(seed, scale, cols, rows, dens, entered, state)
    for scale, cols, rows, dens in ALT_DIMS:
        for state in STATES:
            add(SEEDS[0], scale, cols, rows, dens, 37.5, state)
    for scale, (cols, rows, dens) in dots.SCALES.items():     # idle-twinkle setting off: tonic only
        for seed in SEEDS[:2]:
            add(seed, scale, cols, rows, dens, 0.0, "idle", twinkle=False)
    return out


def render() -> str:
    doc = {"schema": "cf2909.dots-vectors/1",
           "generator": "tools/gen-dots-vectors.py (oracle: python/domain/dots.py)",
           "cell": "[x, y, glyph, r, g, b, pigment] for every VISIBLE organ (glyph != ' '), constellation order",
           "scenes": scenes()}
    head = json.dumps({k: v for k, v in doc.items() if k != "scenes"}, ensure_ascii=False)[:-1]
    return head + ',\n"scenes": [\n' + ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in doc["scenes"]) + "\n]}\n"


def main(argv: list[str]) -> int:
    text = render()
    n = text.count('{"seed"')
    if "--check" in argv:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run python3 tools/gen-dots-vectors.py", file=sys.stderr)
            return 1
        print(f"dots-vectors fresh: {n} scenes")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {n} scenes, {len(text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
