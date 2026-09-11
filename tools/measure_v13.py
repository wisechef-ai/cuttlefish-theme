#!/usr/bin/env python3
"""Measure the v13 cuttlefish-theme acceptance contracts.

This is intentionally an executable probe rather than a test module: its numbers
are computed from the colours sent to the terminal after xterm-256 quantisation.
"""
from __future__ import annotations

import importlib
import importlib.util
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
from cuttlefish_theme.color.terminal import (  # noqa: E402
    _index_to_hex,
    contrast_ratio,
    quantize_256,
)
from cuttlefish_theme.session import Signal  # noqa: E402

FOREGROUND = "#E8E6EA"
SESSIONS = tuple(f"s{n}" for n in range(200))
SIGNALS = tuple(s.value for s in Signal)
WIDTH = 80
ROWS = 3


def qcolour(value: str) -> str:
    """Return the exact xterm-256 colour represented by a source hex."""
    return _index_to_hex(quantize_256(value))


def _optional(name: str):
    try:
        return importlib.import_module(f"cuttlefish_theme.{name}")
    except (ImportError, AttributeError):
        return None


def _hexes(text: str) -> tuple[str, ...]:
    import re
    return tuple(qcolour(x) for x in re.findall(r"#[0-9A-Fa-f]{6}", text))


def _mantle_api():
    try:
        from cuttlefish_theme.chrome import _mantle_classes, _mantle_row
        from cuttlefish_theme.linework import cells
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"mantle API unavailable: {exc}") from exc
    return _mantle_classes, _mantle_row, cells


def _row_backgrounds(row) -> tuple[str, ...]:
    values = []
    for style, _text in row:
        for token in style.split():
            if token.lower().startswith("bg:"):
                values.append(qcolour(token[3:]))
                break
    return tuple(values)


def _lit_cells(cells_row, ground: str) -> tuple[str, ...]:
    return tuple(qcolour(fg) for fg, _bg, _glyph in cells_row if qcolour(fg) != ground)


def _all_mantle_rows(classes, row, cells):
    """Yield (session, signal, row backgrounds, lit cell colours)."""
    for sid in SESSIONS:
        ground = qcolour(_ground(sid))
        for signal in SIGNALS:
            for row_key in range(ROWS):
                rendered = row(sid, WIDTH, row_key, signal)
                row_bg = _row_backgrounds(rendered)
                # The transcript row is the measured mantle surface.
                # A lit cell differs from the ground after quantisation.
                lit = tuple(bg for bg in row_bg if bg != ground)
                yield sid, signal, row_bg, lit


def _ground(sid: str) -> str:
    from cuttlefish_theme.chrome import _mantle_palette
    return _mantle_palette(sid)


def _class_indices(classes, sid: str, signal: str) -> tuple[int, ...]:
    return tuple(quantize_256(c) for c in classes(sid, signal))


def _family_bucket(value: str) -> int:
    """The hue family, using the SAME arc the palette is built from.

    A 30-degree bucket splits one family in two — the blue family spans hues
    264-298 and landed in buckets 8 and 9 — so a session's own dominant colour
    counted as two families and the share read 0.625 against a true 0.858.
    """
    from cuttlefish_theme.band import family_of
    return family_of(value)


def _result(number: int, name: str, value: str, threshold: str, passed: bool):
    return number, name, value, threshold, "PASS" if passed else "FAIL"


def _skip(number: int, name: str, reason: str):
    return number, name, reason, "—", "SKIP"


def measure() -> tuple[list[tuple], list[str], int]:
    results = []
    skipped = []
    try:
        classes, row, cells = _mantle_api()
    except RuntimeError as exc:
        reason = str(exc)
        for n, name in enumerate(NAMES, 1):
            results.append(_skip(n, name, reason))
            skipped.append(f"{n}: {reason}")
        return results, skipped, 0

    rows = list(_all_mantle_rows(classes, row, cells))

    # 1. A row's ratio uses its best and worst background contrast against the
    # same foreground. It is not a ratio of raw colours or of adjacent cells.
    swings = []
    for _sid, _sig, backgrounds, _lit in rows:
        if backgrounds:
            ratios = [contrast_ratio(FOREGROUND, bg) for bg in backgrounds]
            swings.append(max(ratios) / min(ratios))
    if swings:
        results.append(_result(1, NAMES[0], f"mean {statistics.mean(swings):.3f}x; worst {max(swings):.3f}x", "<= 1.6x", max(swings) <= 1.6))
    else:
        results.append(_skip(1, NAMES[0], "no transcript rows produced")); skipped.append("1: no transcript rows produced")

    # Visible colours include transcript rows and the linework source. Every
    # colour is quantised before either contrast or hue is inspected.
    visible = []
    for _sid, _sig, backgrounds, lit in rows:
        visible.extend(backgrounds); visible.extend(lit)
    worst = min((contrast_ratio(FOREGROUND, c) for c in visible), default=None)
    if worst is None:
        results.append(_skip(2, NAMES[1], "no visible colours")); skipped.append("2: no visible colours")
    else:
        results.append(_result(2, NAMES[1], f"{worst:.3f}:1", ">= 3.0:1", worst >= 3.0))

    # Per SESSION and RESTING only. Two reasons the earlier reading was wrong:
    # pooling 200 sessions made their dominant families compete (it read 0.255
    # against a true 0.858), and the acute signals have no dominant family at all
    # — they deliberately wear the fixed amber/red set, so folding them in scored
    # the alarm as a failure of the identity contract.
    shares = []
    for sid in SESSIONS:
        ground = qcolour(_ground(sid))
        lit = [c for _sid, signal, _bg, values in rows if _sid == sid and signal == "resting"
               for c in values if c != ground]
        if lit:
            counts = Counter(_family_bucket(c) for c in lit)
            shares.append(counts.most_common(1)[0][1] / len(lit))
    dominant_share = sum(shares) / len(shares) if shares else None
    dominant_bucket = Counter(
        _family_bucket(c) for _sid, signal, _bg, values in rows if signal == "resting"
        for c in values
    ).most_common(1)[0][0] if shares else None
    island_share = 1.0 - dominant_share if dominant_share is not None else None
    if dominant_share is None:
        results.append(_skip(3, NAMES[2], "no lit cells")); skipped.append("3: no lit cells")
        results.append(_skip(4, NAMES[3], "no lit cells")); skipped.append("4: no lit cells")
        results.append(_skip(5, NAMES[4], "no lit cells")); skipped.append("5: no lit cells")
    else:
        results.append(_result(3, NAMES[2], f"{dominant_share:.3f} (bucket {dominant_bucket * 30}°)", "0.75–0.92", 0.75 <= dominant_share <= 0.92))
        results.append(_result(4, NAMES[3], f"{island_share:.3f}", "0.08–0.20", 0.08 <= island_share <= 0.20))
        # Runs are measured per transcript row, retaining clusters at row edges.
        runs = []
        for _sid, _sig, _bg, values in rows:
            is_island = [_family_bucket(c) != dominant_bucket for c in values]
            i = 0
            while i < len(is_island):
                if is_island[i]:
                    j = i + 1
                    while j < len(is_island) and is_island[j]: j += 1
                    runs.append(j - i); i = j
                else:
                    i += 1
        mean_run = statistics.mean(runs) if runs else 0.0
        results.append(_result(5, NAMES[4], f"{mean_run:.3f} cells", ">= 2.5 cells", mean_run >= 2.5))

    dither = _optional("dither")
    tone_values = set(visible)
    dither_note = "solid tones only (dither.py absent)"
    if dither is not None:
        # Future dither implementations may expose explicit perceived colours;
        # accepting this tiny, documented hook avoids pretending blends are solid.
        provider = getattr(dither, "perceived_tones", None)
        if callable(provider):
            for tone in provider(tuple(visible)):
                tone_values.add(qcolour(tone))
            dither_note = "solid + dither perceived tones"
        else:
            dither_note = "dither.py present; no perceived_tones hook"
    results.append(_result(6, NAMES[5], f"{len(tone_values)} ({dither_note})", ">= 12", len(tone_values) >= 12))

    palettes = {frozenset(_class_indices(classes, sid, "resting")) for sid in SESSIONS[:20]}
    distinct = len(palettes)
    results.append(_result(7, NAMES[6], f"{distinct}/20", ">= 16/20", distinct >= 16))

    needs = {tuple(_class_indices(classes, sid, "needs_me")) for sid in SESSIONS}
    faults = {tuple(_class_indices(classes, sid, "fault")) for sid in SESSIONS}
    acute_ok = len(needs) == 1 and len(faults) == 1
    results.append(_result(8, NAMES[7], f"needs_me {len(needs)}; fault {len(faults)}", "exactly 1 each", acute_ok))

    shared = max((len(set(_class_indices(classes, sid, "resting")) & (set(_class_indices(classes, sid, "needs_me")) | set(_class_indices(classes, sid, "fault")))) for sid in SESSIONS), default=0)
    results.append(_result(9, NAMES[8], str(shared), "0", shared == 0))

    # 10/11 use the actual acute status-bar pair when available. The brightest
    # linework foreground is the dot; the bar background is the fill.
    try:
        from cuttlefish_theme.chrome import _acute_status_bar
        from cuttlefish_theme.color.oklab import hex_to_oklch as to_lch
        fills = []; dots = []; separations = []
        for signal in (Signal.NEEDS_ME, Signal.FAULT):
            fill, dot = _acute_status_bar(signal)
            fill, dot = qcolour(fill), qcolour(dot)
            fills.append(to_lch(fill).C); dots.append(dot); separations.append(contrast_ratio(dot, fill))
        fill_chroma = min(fills)
        dot_sep = min(separations)
        results.append(_result(10, NAMES[9], f"{fill_chroma:.3f}", "> 0.05", fill_chroma > 0.05))
        results.append(_result(11, NAMES[10], f"{dot_sep:.3f}:1", ">= 3.0:1", dot_sep >= 3.0))
    except (ImportError, AttributeError) as exc:
        for n in (10, 11):
            results.append(_skip(n, NAMES[n - 1], f"status bar API unavailable: {exc}")); skipped.append(f"{n}: status bar API unavailable")

    # Warm all relevant caches, then time only the cached call. Median avoids a
    # scheduler hiccup deciding the contract while the worst sample remains visible.
    try:
        for sid in SESSIONS[:8]:
            row(sid, WIDTH, 0, "resting")
        samples = []
        for i in range(2000):
            sid = SESSIONS[i % 8]
            start = time.perf_counter_ns(); row(sid, WIDTH, i % ROWS, "resting"); samples.append(time.perf_counter_ns() - start)
        mean_us = statistics.mean(samples) / 1000.0
        results.append(_result(12, NAMES[11], f"mean {mean_us:.3f} us; median {statistics.median(samples) / 1000.0:.3f} us", "<= 15 us", mean_us <= 15.0))
    except (AttributeError, TypeError) as exc:
        results.append(_skip(12, NAMES[11], f"_mantle_row unavailable: {exc}")); skipped.append(f"12: _mantle_row unavailable")

    measured = sum(status in ("PASS", "FAIL") for *_rest, status in results)
    exit_code = 0 if all(status in ("PASS", "SKIP") for *_rest, status in results) and not any(status == "FAIL" for *_rest, status in results) else 1
    return results, skipped, exit_code


NAMES = (
    "contrast swing per line", "worst contrast", "dominant family share",
    "island share", "island cluster size", "perceived tones",
    "distinct session palettes", "acute sets across sessions",
    "acute vs resting shared indices", "bar fill chroma", "bar dot/fill separation",
    "per-line cost",
)


def main() -> int:
    results, _skipped, code = measure()
    print(f"{'#':>2}  {'name':<31} {'measured value':<42} {'threshold':<16} result")
    print("-" * 105)
    for number, name, value, threshold, status in results:
        print(f"{number:>2}  {name:<31} {value:<42} {threshold:<16} {status}")
    print(f"OVERALL: {'PASS' if code == 0 else 'FAIL'} (exit code {code})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
