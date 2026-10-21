"""Behaviour contract for tools/dots_preview.py — the sparse-dots oracle (Adam, 2026-10-21).

Asserts on what the user sees (painted cells, emitted bytes), never on source text.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pty
import re
import select
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "dots_preview.py"
_spec = importlib.util.spec_from_file_location("dots_preview", TOOL)
assert _spec and _spec.loader
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)

COLS, ROWS = 120, 24
STATES = list(dp.FPS)


def settle(state: str, secs: float = 2.4, session: str = "s1", rows: int = ROWS):
    """Run the real kinetics for *secs* and return {(x, y): (glyph, rgb, pigment)}."""
    organs = dp.constellation(session, COLS, rows, 0.10)
    fps = dp.FPS[state]
    n = int(secs * fps)
    for i in range(n + 1):
        for o in organs:
            target, _ = dp.drive(o, state, 1000.0 + i / fps, i / fps, COLS, rows)
            dp.step_kinetics(o, target, 1 / fps)
    out = {}
    for o in organs:
        _, pig = dp.drive(o, state, 1000.0 + n / fps, n / fps, COLS, rows)
        g, rgb = dp.appearance(o, o.e, pig, dp.session_hue(session))
        out[o.x, o.y] = (g, rgb, pig)
    return out


def test_a_session_keeps_its_constellation_and_sessions_differ():
    a = [(o.x, o.y) for o in dp.constellation("s1", COLS, ROWS, 0.10)]
    assert a == [(o.x, o.y) for o in dp.constellation("s1", COLS, ROWS, 0.10)]
    assert a != [(o.x, o.y) for o in dp.constellation("s2", COLS, ROWS, 0.10)]


def test_organs_are_sparse_and_never_touch():
    pos = {(o.x, o.y) for o in dp.constellation("s1", COLS, ROWS, 0.10)}
    assert 0.02 < len(pos) / (COLS * ROWS) < 0.10
    assert not any((x + dx, y + dy) in pos
                   for x, y in pos for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


def test_identity_hue_never_lands_in_the_alarm_arc():
    for i in range(500):
        h = dp.session_hue(f"s{i}")
        assert 110 <= h < 340, h


def test_opening_is_faster_than_closing():
    o = dp.constellation("s1", COLS, ROWS, 0.10)[0]
    o.e = 0.0
    dp.step_kinetics(o, 1.0, 0.1)
    opened = o.e
    o.e = 1.0
    dp.step_kinetics(o, 0.0, 0.1)
    assert opened > 2 * (1.0 - o.e)


@pytest.mark.parametrize("state", STATES)
def test_every_state_paints_something_and_only_alarms_use_alarm_pigment(state):
    cells = settle(state)
    lit = [c for c in cells.values() if c[1] is not None]
    assert lit, state
    pigments = {c[2] for c in lit}
    if state == "needs-you":
        assert "amber" in pigments and "red" not in pigments
    elif state == "fault":
        assert pigments == {"red"}  # blanched: only the red margin is left open
    else:
        assert pigments <= {"id", "glint"}


def test_states_differ_in_a_still_frame():
    frames = {s: frozenset(settle(s).items()) for s in STATES}
    assert len(set(frames.values())) == len(STATES)


def test_working_is_busier_than_idle():
    def changes(state):
        prev, n = settle(state, 2.0), 0
        for t in (2.5, 3.0, 3.5):
            cur = settle(state, t)
            n += sum(prev[k] != cur[k] for k in cur)
            prev = cur
        return n

    assert changes("thinking") > 3 * max(1, changes("idle"))


def test_fault_is_static_once_blanched():
    assert settle("fault", 3.0) == settle("fault", 4.0)


def test_appearance_is_quantised_so_invisible_changes_cost_nothing():
    o = dp.constellation("s1", COLS, ROWS, 0.10)[0]
    h = dp.session_hue("s1")
    assert dp.appearance(o, 0.500, "id", h) == dp.appearance(o, 0.504, "id", h)
    assert dp.appearance(o, 0.05, "id", h) == (" ", None)


def _pty_run(args, secs):
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, str(TOOL), *args])
    import fcntl
    import termios
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, COLS, 0, 0))

    def drain(s):
        b, t0 = b"", time.time()
        while time.time() - t0 < s:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    b += os.read(fd, 65536)
                except OSError:
                    break
        return b

    out = drain(secs)
    os.kill(pid, 2)
    out += drain(1.0)
    _, status = os.waitpid(pid, 0)
    return out, status


@pytest.mark.parametrize("args", [["--state", "tool"], ["--field", "--state", "thinking"]])
def test_terminal_never_paints_a_background_and_restores_on_exit(args):
    out, status = _pty_run(args, 2.0)
    assert status == 0
    assert not re.search(rb"\x1b\[(?:[0-9;]*;)?48;", out)  # no background SGR
    assert b"\x1b]11" not in out  # no OSC 11
    assert b"\x1b[38;2;" in out  # dots were actually drawn
    assert out.rstrip().endswith(b"\x1b[?1049l")  # alt screen left, terminal handed back


def test_refuses_without_a_terminal():
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 1 and "real terminal" in r.stderr
    assert "\x1b" not in r.stdout


def test_png_still_renders(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    png = tmp_path / "f.png"
    dp.run_png(argparse.Namespace(png=str(png), state="needs-you", t=2.0, cols=COLS, rows=3,
                                  field=False, session="s1", density=0.13, bg="#1e1e1e"))
    with Image.open(png) as im:
        assert len(im.getcolors(1 << 16) or ()) > 2  # ground + identity organs + amber
