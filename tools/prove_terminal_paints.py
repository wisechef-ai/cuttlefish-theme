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

# The window colour the theme sets via OSC 11, and therefore the background the
# field's unlit cells must land on exactly.
TERMINAL_GROUND = (0x0B, 0x0C, 0x10)

# Stock Hermes gold. If these dominate, the theme did not load and the host's
# own palette is on screen — the failure mode that looks like success.
STOCK_PALETTE = {(0xFF, 0xD7, 0x00), (0xCD, 0x7F, 0x32), (0xB8, 0x86, 0x0B),
                 (0xFF, 0xF8, 0xDC), (0xFF, 0xBF, 0x00), (0x1A, 0x1A, 0x2E)}

_TRUECOLOR_BG = re.compile(rb"\x1b\[[0-9;]*?48;2;(\d{1,3});(\d{1,3});(\d{1,3})")
_INDEXED_BG = re.compile(rb"\x1b\[[0-9;]*?48;5;(\d{1,3})")

CAPTURE_SECONDS = 25.0


def _spawn_hermes() -> tuple[int, subprocess.Popen[bytes]]:
    """Start `hermes` on a pty wide enough to show the chrome."""
    master, slave = pty.openpty()
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        # VTE and most modern emulators are 24-bit but advertise nothing, and
        # prompt_toolkit then quantises every hex onto the 256 cube.
        "COLORTERM": "truecolor",
        "HERMES_PROVE_PAINT": "1",
    }
    proc = subprocess.Popen(
        ["hermes"], stdin=slave, stdout=slave, stderr=slave,
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


def _backgrounds(captured: bytes) -> tuple[list[tuple[int, int, int]], int]:
    """Every background colour the terminal was asked to paint."""
    truecolor = [tuple(int(c) for c in m.groups()) for m in _TRUECOLOR_BG.finditer(captured)]
    indexed = len(_INDEXED_BG.findall(captured))
    return truecolor, indexed


def main() -> int:
    print("spawning a real `hermes` on a pty ...")
    master, proc = _spawn_hermes()
    try:
        captured = _capture(master, CAPTURE_SECONDS)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)
        os.close(master)

    print(f"captured {len(captured):,} bytes\n")
    if not captured:
        print("FAIL: the process painted nothing at all")
        return 1

    truecolor, indexed = _backgrounds(captured)
    counts = Counter(truecolor)

    checks: list[tuple[str, bool, str]] = []

    checks.append((
        "the terminal received truecolor backgrounds",
        len(truecolor) > 50,
        f"{len(truecolor)} truecolor bg escapes, {indexed} indexed",
    ))

    ground_hits = counts.get(TERMINAL_GROUND, 0)
    checks.append((
        "the field's ground colour reached the screen",
        ground_hits > 0,
        f"#0b0c10 painted {ground_hits} times",
    ))

    distinct = len(counts)
    checks.append((
        "the painted surface is textured, not flat",
        distinct >= 8,
        f"{distinct} distinct background colours",
    ))

    stock_hits = sum(counts.get(c, 0) for c in STOCK_PALETTE)
    checks.append((
        "the stock Hermes palette is NOT dominating",
        stock_hits * 4 < len(truecolor) if truecolor else False,
        f"{stock_hits} stock-palette cells of {len(truecolor)}",
    ))

    dark = sum(n for rgb, n in counts.items() if sum(rgb) <= 120)
    checks.append((
        "most of the frame is dark, as cuttlefish skin is",
        dark * 2 >= len(truecolor) if truecolor else False,
        f"{dark} dark cells of {len(truecolor)}",
    ))

    width = max(len(label) for label, _, _ in checks)
    failed = 0
    for label, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}  {detail}")
        failed += not ok

    print()
    if failed:
        print(f"{failed} of {len(checks)} checks failed — the terminal did not paint the theme")
        return 1
    print("the real terminal paints the cuttlefish theme")
    return 0


if __name__ == "__main__":
    sys.exit(main())
