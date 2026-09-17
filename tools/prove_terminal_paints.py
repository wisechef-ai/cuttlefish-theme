#!/usr/bin/env python3
"""Proof that a REAL `hermes` CLI paints the cuttlefish theme.

Every other test in this repo asks the engine what colour it would produce.
This one spawns the actual binary on a pseudo-terminal, reads the bytes it
writes to the screen, and asserts the theme's colours are in them.

That distinction has decided this project repeatedly: four separate rounds
shipped a fully green suite while the user saw an unthemed terminal, because
"the engine returns correct colours" and "the terminal shows them" are two
different claims and only one of them was ever tested.

Run:  python3 tools/prove_terminal_paints.py
Exit: 0 if the real terminal painted the theme, 1 otherwise.
"""

from __future__ import annotations

import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from collections import Counter

RGB = tuple[int, int, int]

# The window colour the theme sets via OSC 11, and therefore the background the
# field's unlit cells must land on exactly.
TERMINAL_GROUND: RGB = (0x0B, 0x0C, 0x10)

# Stock Hermes gold. If these dominate, the theme did not load and the host's
# own palette is on screen — the failure mode that looks like success.
STOCK_PALETTE = {(0xFF, 0xD7, 0x00), (0xCD, 0x7F, 0x32), (0xB8, 0x86, 0x0B),
                 (0xFF, 0xF8, 0xDC), (0xFF, 0xBF, 0x00), (0x1A, 0x1A, 0x2E)}

_TRUECOLOR_BG = re.compile(rb"\x1b\[[0-9;]*?48;2;(\d{1,3});(\d{1,3});(\d{1,3})")
_INDEXED_BG = re.compile(rb"\x1b\[[0-9;]*?48;5;(\d{1,3})")

CAPTURE_SECONDS = 25.0
# WHY: a themed frame paints hundreds of cells; 50 rules out a stray accent
# without pinning the exact count, which varies with banner content.
MIN_BG_ESCAPES = 50
# WHY: the field is sparse but never flat — 8 tones is far below the ~60
# measured, and catches a collapse to a single colour.
MIN_DISTINCT_COLOURS = 8
# WHY: sum(rgb) <= 120 is the dark band; cuttlefish skin is mostly dark
# ground with sparse bright pigment.
DARK_CELL_LUMA = 120


def _spawn_hermes(argv: list[str]) -> tuple[int, subprocess.Popen[bytes]]:
    """Start a hermes entrypoint on a pty wide enough to show the chrome."""
    master, slave = pty.openpty()
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        # VTE and most modern emulators are 24-bit but advertise nothing, and
        # prompt_toolkit then quantises every hex onto the 256 cube.
        "COLORTERM": "truecolor",
    }
    proc = subprocess.Popen(
        argv, stdin=slave, stdout=slave, stderr=slave,
        env=env, preexec_fn=os.setsid, close_fds=True,
    )
    os.close(slave)
    return master, proc


def _capture(master: int, seconds: float) -> bytes:
    """Read everything the process paints, until it goes quiet."""
    chunks: list[bytes] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.5)
        if not ready:
            continue
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks)


def _backgrounds(captured: bytes) -> tuple[list[RGB], int]:
    """Every background colour the terminal was asked to paint."""
    truecolor: list[RGB] = [
        (int(r), int(g), int(b)) for r, g, b in (m.groups() for m in _TRUECOLOR_BG.finditer(captured))
    ]
    return truecolor, len(_INDEXED_BG.findall(captured))


ENTRYPOINTS: tuple[list[str], ...] = (["hermes"], ["hermes", "chat"])


def _capture_entrypoint(argv: list[str]) -> bytes:
    """Run one entrypoint to quiescence and return everything it painted."""
    master, proc = _spawn_hermes(argv)
    try:
        return _capture(master, CAPTURE_SECONDS)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)
        os.close(master)


def _checks_for(captured: bytes) -> list[tuple[str, bool, str]]:
    """Score one captured stream against every property the theme promises."""
    truecolor, indexed = _backgrounds(captured)
    counts = Counter(truecolor)
    stock_hits = sum(counts.get(colour, 0) for colour in STOCK_PALETTE)
    dark = sum(n for rgb, n in counts.items() if sum(rgb) <= DARK_CELL_LUMA)
    return [
        ("the terminal received truecolor backgrounds",
         len(truecolor) > MIN_BG_ESCAPES,
         f"{len(truecolor)} truecolor bg escapes, {indexed} indexed"),
        ("the field's ground colour reached the screen",
         counts.get(TERMINAL_GROUND, 0) > 0,
         f"#0b0c10 painted {counts.get(TERMINAL_GROUND, 0)} times"),
        ("the painted surface is textured, not flat",
         len(counts) >= MIN_DISTINCT_COLOURS,
         f"{len(counts)} distinct background colours"),
        ("the stock Hermes palette is NOT dominating",
         stock_hits * 4 < len(truecolor) if truecolor else False,
         f"{stock_hits} stock-palette cells of {len(truecolor)}"),
        ("most of the frame is dark, as cuttlefish skin is",
         dark * 2 >= len(truecolor) if truecolor else False,
         f"{dark} dark cells of {len(truecolor)}"),
    ]


def _report(argv: list[str], captured: bytes) -> int:
    """Print one entrypoint's scorecard; return the number of failures."""
    command = " ".join(argv)
    print(f"=== `{command}` — captured {len(captured):,} bytes")
    if not captured:
        print("  [FAIL] the process painted nothing at all\n")
        return 1
    checks = _checks_for(captured)
    width = max(len(label) for label, _, _ in checks)
    failed = 0
    for label, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}  {detail}")
        failed += not ok
    print()
    return failed


def main() -> int:
    """Prove BOTH entrypoints paint.

    `hermes` and `hermes chat` are different subcommands and a user may type
    either, so proving one proves half the promise. They are checked
    separately rather than combined: a regression in one must not be masked by
    the other still painting.
    """
    failed = 0
    for argv in ENTRYPOINTS:
        print(f"spawning a real `{' '.join(argv)}` on a pty ...")
        failed += _report(argv, _capture_entrypoint(argv))

    if failed:
        print(f"{failed} check(s) failed — the terminal did not paint the theme")
        return 1
    print("every hermes entrypoint paints the cuttlefish theme")
    return 0


if __name__ == "__main__":
    sys.exit(main())
