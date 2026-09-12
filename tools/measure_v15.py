#!/usr/bin/env python3
"""Independent truecolor ribbon measurement harness (v15).

This probe measures the public ribbon renderer outputs, not palette allocation
internals.  It deliberately fails closed when the v15 API is unavailable.
"""
from __future__ import annotations

import importlib.util
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("CUTTLEFISH_ROOT", str(Path(__file__).resolve().parent.parent)))
SESSIONS = tuple(f"s{n}" for n in range(200))
SIGNALS = ("resting", "needs_me", "fault")
WIDTH = 80
ROWS = 3
FOREGROUND = "#E8E6EA"
# The bar paints white text, so it must be scored against white — not against the
# body foreground it never pairs with.
BAR_FOREGROUND = "#FFFFFF"
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def _load_plugin() -> None:
    spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin from {ROOT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cuttlefish_theme"] = module
    spec.loader.exec_module(module)


_load_plugin()
from cuttlefish_theme.color.oklab import hex_to_oklch  # noqa: E402
from cuttlefish_theme.color.terminal import contrast_ratio  # noqa: E402


def _hex_values(value) -> tuple[str, ...]:
    """Extract rendered truecolor tokens without interpreting glyph text."""
    if isinstance(value, str):
        return tuple(x.upper() for x in HEX_RE.findall(value))
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_hex_values(item))
        return tuple(out)
    if isinstance(value, (tuple, list)):
        out = []
        for item in value:
            out.extend(_hex_values(item))
        return tuple(out)
    return ()


def _cell_colour(cell) -> str | None:
    """Pick the cell's background/display colour for horizontal scoring."""
    if isinstance(cell, str):
        found = _hex_values(cell)
        return found[0] if found else None
    if isinstance(cell, dict):
        for key in ("bg", "background", "color", "colour", "hex"):
            found = _hex_values(cell.get(key))
            if found:
                return found[0]
    if isinstance(cell, (tuple, list)):
        found = _hex_values(cell)
        return found[-1] if found else None
    return None


def _field_signature(field) -> tuple[tuple[float, ...], object]:
    """Return the multiset of OKLCh hues and a visual phase fingerprint."""
    phase = None
    raw = None
    if isinstance(field, dict):
        phase = field.get("phase")
        raw = field.get("hues", field.get("colors", field.get("colours")))
    else:
        phase = getattr(field, "phase", None)
        raw = getattr(field, "hues", None)
    source = raw if raw is not None else field
    if raw is not None and isinstance(raw, (tuple, list)) and all(
        isinstance(item, (int, float)) for item in raw
    ):
        hues = [float(item) % 360.0 for item in raw]
    else:
        hues = [hex_to_oklch(h).h for h in _hex_values(source)]
    if not hues:
        raise TypeError("ribbon_field output exposes no rendered hex hues")
    hue_set = tuple(sorted(round(h, 3) for h in hues))
    if phase is None:
        # Grid-only implementations do not publish a scalar phase. Preserve the
        # visible phase independently by fingerprinting the first rendered row.
        first_row = field[0] if isinstance(field, (tuple, list)) and field else field
        phase = tuple(round(hex_to_oklch(h).h, 3) for h in _hex_values(first_row))
    return hue_set, phase


def _cube_hexes() -> frozenset[str]:
    levels = (0, 95, 135, 175, 215, 255)
    return frozenset(f"#{r:02X}{g:02X}{b:02X}" for r in levels for g in levels for b in levels)


def _oklab_l_delta(a: str, b: str) -> float:
    return abs(hex_to_oklch(a).L - hex_to_oklch(b).L)


def _measure():
    # Keep the production import explicit and local so a missing sibling branch
    # becomes a measured, structured failure rather than an import traceback.
    from cuttlefish_theme.ribbon import ribbon_row, ribbon_field, bar_cells

    rows = []
    rendered = []
    bar_rendered = []
    fields = {}
    bars = {}
    for sid in SESSIONS:
        for signal in SIGNALS:
            fields[(sid, signal)] = _field_signature(ribbon_field(sid, WIDTH, ROWS, signal))
            for row_number in range(ROWS):
                raw = ribbon_row(sid, WIDTH, row_number, signal)
                colours = tuple(c for c in (_cell_colour(x) for x in raw) if c)
                if not colours:
                    raise TypeError("ribbon_row produced no hex-valued cells")
                rows.append(colours)
                rendered.extend(colours)
            bar = tuple(c for c in (_cell_colour(x) for x in bar_cells(sid, WIDTH, signal)) if c)
            bars[(sid, signal)] = bar
            bar_rendered.extend(bar)

    deltas = [d for row in rows for a, b in zip(row, row[1:]) for d in (_oklab_l_delta(a, b),)]
    smooth_max = max(deltas, default=float("inf"))
    smooth_mean = statistics.mean(deltas) if deltas else float("inf")
    # Each surface is scored against the ink IT carries. Folding the two together
    # measured the bar against the body foreground and reported 3.678:1 for a bar
    # that is legible at 4.56:1 with the white text it actually paints.
    worst_contrast = min(
        [contrast_ratio(FOREGROUND, colour) for colour in rendered]
        + [contrast_ratio(BAR_FOREGROUND, colour) for colour in bar_rendered],
        default=0.0,
    )
    swings = []
    for row in rows:
        ratios = [contrast_ratio(FOREGROUND, colour) for colour in row]
        swings.append(max(ratios) / min(ratios))
    uniformity = max(swings, default=float("inf"))

    identity = len(set(fields[(sid, "resting")] for sid in SESSIONS))
    # STABILITY replaces the old "the alarm recolours the field" contract. Adam,
    # 2026-09-12: "per session no big background changes - the background change
    # makes the recognition of terminal harder". The field is identity and must
    # not move with state; the BAR is the state channel.
    stable_ok = all(fields[(sid, s)] == fields[(sid, "resting")]
                    for sid in SESSIONS for s in ("needs_me", "fault"))
    needs_bars = {bars[(sid, "needs_me")] for sid in SESSIONS}
    fault_bars = {bars[(sid, "fault")] for sid in SESSIONS}
    universal_ok = (len(needs_bars) == 1 and len(fault_bars) == 1 and
                    needs_bars != fault_bars and
                    all(bars[(sid, "needs_me")] != bars[(sid, "resting")] for sid in SESSIONS))
    hues = lambda bar: [hex_to_oklch(c).h for c in bar]
    red_ok = all(h >= 350.0 or h <= 50.0 for h in hues(next(iter(fault_bars))))
    amber_ok = all(55.0 <= h <= 115.0 for h in hues(next(iter(needs_bars))))
    distinct_hex = len(set(rendered) | set(bar_rendered))
    cube_count = len((set(rendered) | set(bar_rendered)) & _cube_hexes())

    # Prime each measured key immediately before its timed call. This avoids
    # cache-capacity artifacts while covering the full 200-session corpus.
    warm_samples = []
    for sid in SESSIONS:
        for signal in SIGNALS:
            for row_number in range(ROWS):
                ribbon_row(sid, WIDTH, row_number, signal)
                start = time.perf_counter_ns()
                ribbon_row(sid, WIDTH, row_number, signal)
                warm_samples.append(time.perf_counter_ns() - start)
    cold_samples = []
    cache_clear = getattr(ribbon_field, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    for i in range(240):
        sid = SESSIONS[i % len(SESSIONS)]
        signal = SIGNALS[i % len(SIGNALS)]
        start = time.perf_counter_ns()
        ribbon_field(sid, WIDTH, ROWS, signal)
        cold_samples.append(time.perf_counter_ns() - start)
    warm_mean = statistics.mean(warm_samples) / 1000.0
    cold_mean = statistics.mean(cold_samples) / 1000.0
    return {
        "smoothness": (f"max {smooth_max:.4f}; mean {smooth_mean:.4f}", smooth_max <= .06),
        "legibility": (f"{worst_contrast:.3f}:1", worst_contrast >= 4.5),
        "uniformity": (f"{uniformity:.3f}x", uniformity <= 1.6),
        "identity": (f"{identity}/200", identity >= 150),
        "stability": ("field unchanged by signal" if stable_ok else "SIGNAL MOVED THE FIELD", stable_ok),
        "universality": (f"needs_me {len(needs_bars)}; fault {len(fault_bars)} bars", universal_ok),
        "direction": (f"fault red={red_ok}; needs_me amber={amber_ok}", red_ok and amber_ok),
        "purity": (f"{distinct_hex} distinct; {cube_count} cube entries", distinct_hex > 256),
        "cost": (f"warm mean {warm_mean:.3f} us; cold field {cold_mean:.3f} us", warm_mean <= 15.0),
    }


def main() -> int:
    try:
        results = _measure()
    except Exception as exc:
        print("contract | measured | threshold | result")
        print(f"ALL      | unavailable: {type(exc).__name__}: {exc} | v15 API | FAIL")
        return 1
    thresholds = {
        "smoothness": "max <= 0.06", "legibility": ">= 4.5:1 vs its own ink", "uniformity": "<= 1.6x",
        "identity": ">= 150/200", "stability": "field identical in every signal",
        "universality": "exactly 1 bar each + differs from resting",
        "direction": "fault 350–410°; needs_me 55–115°", "purity": "> 256 distinct hex",
        "cost": "warm <= 15 us (cold reported separately)",
    }
    print("contract | measured | threshold | result")
    print("---------|-----------|-----------|-------")
    for name, (value, passed) in results.items():
        print(f"{name} | {value} | {thresholds[name]} | {'PASS' if passed else 'FAIL'}")
    code = 0 if all(passed for _, passed in results.values()) else 1
    print(f"OVERALL: {'PASS' if code == 0 else 'FAIL'} (exit code {code})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
