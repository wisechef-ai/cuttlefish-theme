#!/usr/bin/env python3
"""Prove the cuttlefish skin never makes ``hermes --tui`` paint the terminal background (OSC 11).

    python3 tools/osc11_capture.py [--hermes PATH] [--seconds 8] [--control]

Runs in a THROWAWAY HERMES_HOME (never ~/.hermes): installs ``skins/cuttlefish.yaml``, sets ``display.skin``,
launches ``hermes --tui`` on a pty, records every byte for N seconds, and counts OSC 11 sequences:

  * SET   = ESC ] 11 ; <colour> (BEL | ESC \\)   a real repaint of the terminal background. Must be 0.
  * QUERY = ESC ] 11 ; ?                           the TUI asking the terminal what its background is (read-only).

``--control`` is a positive control for the probe itself (a probe that cannot fail proves nothing): it runs a stub
that writes a real OSC 11 SET through the same pty/regex path and requires >= 1 SET. (A TUI run with a skin that
carries a ``background`` was tried first as the control: upstream's TUI emits only the read-only QUERY for it, never
a SET, so it cannot serve.) Exit 0 iff every expectation holds.

Also checks, with the loader of the Hermes that is importable in THIS interpreter (when there is one), that the
cuttlefish skin's resolved ``background`` equals the stock default skin's. Stdlib only.
"""
import argparse
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET_RE = re.compile(rb"\x1b\]11;(?!\?)[^\x07\x1b]*(?:\x07|\x1b\\)")
QUERY_RE = re.compile(rb"\x1b\]11;\?(?:\x07|\x1b\\)")
ANY_RE = re.compile(rb"\x1b\]11;")

OFFER_VERSION = os.environ.get("CF_OFFER_VERSION", "2")
CONTROL_SKIN = 'name: osc11control\ncolors:\n  background: "#101418"\n  banner_title: "#1fbcea"\n'


def capture(hermes, home, seconds, argv=None):
    """Bytes ``hermes --tui`` writes to its pty in ``seconds``. Answers terminal queries minimally (DA1, OSC 11)."""
    env = dict(os.environ, HERMES_HOME=str(home), TERM="xterm-256color", COLORTERM="truecolor", COLUMNS="120",
               LINES="30", NO_COLOR="")
    env.pop("NO_COLOR")
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(hermes, argv or [hermes, "--tui"], env)
    try:
        import fcntl
        import struct
        import termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    except Exception:  # noqa: BLE001
        pass
    buf, end = bytearray(), time.time() + seconds
    answered = 0
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if not r:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if QUERY_RE.search(chunk) and answered < 3:   # behave like a real terminal: report a dark-ish background
            os.write(fd, b"\x1b]11;rgb:1010/1414/1818\x1b\\")
            answered += 1
        if b"\x1b[c" in chunk:
            os.write(fd, b"\x1b[?62;c")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    os.close(fd)
    return bytes(buf)


def make_home(skin_name, skin_text):
    home = Path(tempfile.mkdtemp(prefix="cf-osc11-"))
    (home / "skins").mkdir()
    (home / "skins" / (skin_name + ".yaml")).write_text(skin_text, encoding="utf-8")
    # answer the first-run shared-metrics offer ("No thanks", settled) so the capture sees the real chat UI, not that prompt
    (home / "config.yaml").write_text("display:\n  skin: %s\ntelemetry:\n  shared_metrics:\n    enabled: false\n    send: false\n    offer_version: %s\n" % (skin_name, OFFER_VERSION), encoding="utf-8")
    return home


def report(label, data):
    sets, queries, anyc = len(SET_RE.findall(data)), len(QUERY_RE.findall(data)), len(ANY_RE.findall(data))
    print("%-9s bytes=%d  ESC]11; total=%d  SET(repaint)=%d  QUERY(read-only probe)=%d" % (label, len(data), anyc, sets, queries))
    return sets, queries


def resolved_background_check():
    """(ok, text) comparing cuttlefish vs default with whatever hermes_cli.skin_engine this interpreter can import."""
    home = make_home("cuttlefish", (ROOT / "skins" / "cuttlefish.yaml").read_text(encoding="utf-8"))
    os.environ["HERMES_HOME"] = str(home)
    try:
        from hermes_cli import skin_engine as se
    except Exception as e:  # noqa: BLE001
        return None, "hermes_cli not importable here (%s): resolved-background check not run" % type(e).__name__
    try:
        mine, stock = se.load_skin("cuttlefish"), se.load_skin("default")
        a, b = mine.colors.get("background"), stock.colors.get("background")
        return a == b, "resolved background: cuttlefish=%r default=%r (%s)" % (a, b, "equal" if a == b else "DIFFERENT")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes", default=shutil.which("hermes") or "hermes")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--control", action="store_true", help="also prove the probe can see a repaint")
    args = ap.parse_args(argv)
    ok = True
    res, text = resolved_background_check()
    print(text)
    ok &= res is not False
    home = make_home("cuttlefish", (ROOT / "skins" / "cuttlefish.yaml").read_text(encoding="utf-8"))
    try:
        sets, _ = report("cuttlefish", capture(args.hermes, home, args.seconds))
        ok &= sets == 0
        print("  expect SET=0 -> %s" % ("PASS" if sets == 0 else "FAIL"))
    finally:
        shutil.rmtree(home, ignore_errors=True)
    if args.control:
        home = make_home("osc11control", CONTROL_SKIN)
        try:
            stub = [sys.executable, "-c", "import sys,time; sys.stdout.write('\\x1b]11;#101418\\x07'); sys.stdout.flush(); time.sleep(1)"]
            sets, _ = report("control", capture(sys.executable, home, 3, argv=stub))
            ok &= sets >= 1
            print("  expect SET>=1 (stub that paints OSC 11 through the same pty) -> %s" % ("PASS" if sets >= 1 else "FAIL"))
        finally:
            shutil.rmtree(home, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
