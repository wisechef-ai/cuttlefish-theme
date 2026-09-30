"""Behaviour contract for the spike-15 terminal test pattern.

Runs the fixture exactly as a matrix cell does (a subprocess, stdlib only)
and checks the bytes it emits, not its source text.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "spikes" / "15-block-elements-colordepth" / "pattern.py"
BLOCKS = "▀▄█▌▐▖▗▘▝▚▞▙▛▜▟"
SGR = re.compile(r"\x1b\[[0-9;]*m")


def run(env_extra: dict, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env, capture_output=True, timeout=30,
    )


def visible_lines(raw: bytes) -> list:
    return SGR.sub("", raw.decode("utf-8")).splitlines()


class PatternContract(unittest.TestCase):
    def test_every_block_glyph_is_emitted_and_labelled(self):
        out = run({"COLUMNS": "100", "LINES": "40", "COLORTERM": "truecolor", "TERM": "xterm-256color"})
        self.assertEqual(out.returncode, 0, out.stderr)
        text = "\n".join(visible_lines(out.stdout))
        for glyph in BLOCKS:
            self.assertIn(glyph, text, f"missing block glyph U+{ord(glyph):04X}")
            self.assertIn(f"U+{ord(glyph):04X}", text, "glyph not labelled with its codepoint")

    def test_truecolor_foreground_256_and_braille_rows_exist(self):
        out = run({"COLUMNS": "100", "LINES": "40", "COLORTERM": "truecolor", "TERM": "xterm-256color"})
        raw = out.stdout.decode("utf-8")
        self.assertRegex(raw, r"\x1b\[38;2;\d+;\d+;\d+m", "no SGR 38;2 truecolor foreground")
        self.assertRegex(raw, r"\x1b\[38;5;\d+m", "no SGR 38;5 256-colour rung")
        text = "\n".join(visible_lines(out.stdout))
        self.assertRegex(text, r"[\u2801-\u28ff]{8,}", "no Braille comparison row")
        for label in ("24-bit", "256", "Braille"):
            self.assertIn(label, text, f"row label {label!r} missing")
        # the 24-bit gradient must actually vary (many distinct colours)
        colours = set(re.findall(r"\x1b\[38;2;(\d+;\d+;\d+)m", raw))
        self.assertGreater(len(colours), 30)

    def test_honours_terminal_width(self):
        for cols in (20, 40, 80, 132):
            out = run({"COLUMNS": str(cols), "LINES": "40", "COLORTERM": "truecolor"})
            self.assertEqual(out.returncode, 0, out.stderr)
            widest = max(len(line) for line in visible_lines(out.stdout))
            self.assertLessEqual(widest, cols, f"a line overflows {cols} columns")

    def test_without_truecolor_still_prints_and_says_so(self):
        out = run({"COLUMNS": "80", "LINES": "40", "TERM": "xterm-256color"})
        self.assertEqual(out.returncode, 0, out.stderr)
        text = "\n".join(visible_lines(out.stdout))
        for glyph in BLOCKS:
            self.assertIn(glyph, text)
        self.assertIn("COLORTERM=(unset)", text)
        self.assertRegex(text, r"(?i)detected depth: 256")
        # the auto rung must not use 24-bit SGR when truecolor isn't advertised
        auto = [l for l in out.stdout.decode().splitlines() if "auto rung" in SGR.sub("", l)]
        self.assertTrue(auto, "no auto rung row")
        self.assertNotIn("38;2;", auto[0])

    def test_deterministic(self):
        env = {"COLUMNS": "90", "LINES": "30", "COLORTERM": "truecolor", "TERM": "xterm-256color"}
        self.assertEqual(run(env).stdout, run(env).stdout)


if __name__ == "__main__":
    unittest.main()
