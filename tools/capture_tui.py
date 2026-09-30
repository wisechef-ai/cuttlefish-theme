#!/usr/bin/env python3
"""Capture a terminal UI: run a command in a terminal, wait for a screen predicate,
write a PNG screenshot and the raw SGR byte log.

Backends
  virtual     pty + pyte virtual terminal; the PNG is rendered from the pyte screen
              model (block elements drawn as geometry, like VTE/iTerm2). No X needed.
  terminator  the real Terminator (VTE) on a user-space Xvfb display; the PNG is a real
              X screenshot of the window. The command's bytes are recorded with
              `script(1)` so the predicate still runs against a pyte model of the screen.

Exit codes
  0  predicate matched; PNG + raw log written
  2  predicate not observed before --timeout (raw log still written, for diagnosis)
  1  any other failure (missing dependency, command could not start, capture failed)

Example
  python3 tools/capture_tui.py --wait-for '▀{20,}' --png out.png --raw-log out.sgr \\
      --cols 120 --rows 40 --timeout 120 -- hermes --tui

Requires: pyte, Pillow (pip install -r tools/requirements-capture.txt).
Terminator mode additionally needs terminator, dbus-run-session, script, and either the
rootless ffmpeg helper ~/.local/opt/xvfb/xvfb-shot.sh or xwd + ImageMagick convert.

Layout: everything above the "I/O shell" marker is pure (argument handling, SGR bytes ->
screen model, predicate matching, PNG rendering from a screen model) and is unit-tested
without a terminal or X; the backends below it do the flaky process/display work.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_TIMEOUT = 0, 1, 2

DEFAULT_TERM = "xterm-256color"
DEFAULT_FONT = "DejaVu Sans Mono 14"
MONO_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Menlo.ttc",
)


# --------------------------------------------------------------------------- config / CLI

@dataclass
class Config:
    command: list[str]
    wait_for: re.Pattern
    png: Path
    raw_log: Path
    mode: str = "virtual"
    timeout: float = 15.0
    settle: float = 0.5
    cols: int = 100
    rows: int = 24
    term: str | None = None          # None = backend default (virtual: xterm-256color; terminator: VTE's own)
    colorterm: str | None = "truecolor"   # None = unset COLORTERM in the child
    env: dict[str, str] = field(default_factory=dict)
    text_out: Path | None = None
    display: str = ":92"
    font: str = DEFAULT_FONT
    geometry: str | None = None      # terminator window WxH in pixels; default derived from cols/rows

    @property
    def effective_term(self) -> str | None:
        if self.term is not None:
            return self.term
        return DEFAULT_TERM if self.mode == "virtual" else None


def _positive(kind):
    def conv(value: str):
        v = kind(value)
        if v <= 0:
            raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
        return v
    return conv


def _env_pair(value: str) -> tuple[str, str]:
    key, sep, val = value.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {value!r}")
    return key, val


def _regex(value: str) -> re.Pattern:
    try:
        return re.compile(value, re.MULTILINE)
    except re.error as exc:
        raise argparse.ArgumentTypeError(f"invalid --wait-for regex {value!r}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capture_tui.py",
        description="Run a command in a terminal, wait until the rendered screen matches a regex, "
                    "then write a PNG screenshot and the raw SGR byte log. Exit 2 on predicate timeout.",
        epilog="Put the command after `--`, e.g.:  capture_tui.py --wait-for READY --png a.png "
               "--raw-log a.sgr -- sh -c 'echo READY; sleep 5'",
    )
    p.add_argument("--mode", choices=("virtual", "terminator"), default="virtual",
                   help="virtual = pty+pyte (no X); terminator = real Terminator on an Xvfb display")
    p.add_argument("--wait-for", required=True, type=_regex, metavar="REGEX",
                   help="Python regex (MULTILINE) matched against the pyte-rendered screen text")
    p.add_argument("--png", required=True, type=Path, help="screenshot output path")
    p.add_argument("--raw-log", required=True, type=Path, help="raw terminal byte (SGR) log output path")
    p.add_argument("--text-out", type=Path, help="also write the final screen text here")
    p.add_argument("--timeout", type=_positive(float), default=15.0, help="max seconds to wait (default 15)")
    p.add_argument("--settle", type=float, default=0.5,
                   help="seconds to keep reading after the match before capturing (default 0.5)")
    p.add_argument("--cols", type=_positive(int), default=100)
    p.add_argument("--rows", type=_positive(int), default=24)
    p.add_argument("--term", help=f"TERM for the child (virtual default {DEFAULT_TERM}; "
                                  "terminator default: whatever VTE sets)")
    p.add_argument("--colorterm", default="truecolor",
                   help="COLORTERM for the child (default truecolor)")
    p.add_argument("--no-colorterm", action="store_true", help="unset COLORTERM in the child (256-colour rung)")
    p.add_argument("--env", action="append", type=_env_pair, default=[], metavar="KEY=VALUE",
                   help="extra environment for the child (repeatable)")
    p.add_argument("--display", default=":92", help="terminator mode: X display (started if not running)")
    p.add_argument("--font", default=DEFAULT_FONT, help=f"terminator mode: font (default {DEFAULT_FONT!r})")
    p.add_argument("--geometry", help="terminator mode: window size WxH in pixels (default from cols/rows)")
    p.add_argument("command", nargs=argparse.REMAINDER, help="command to run (after --)")
    return p


def parse_args(argv: list[str] | None = None) -> Config:
    parser = build_parser()
    ns = parser.parse_args(argv)
    command = ns.command[1:] if ns.command[:1] == ["--"] else ns.command
    if not command:
        parser.error("provide the command to run after --")
    if ns.settle < 0:
        parser.error("--settle must be >= 0")
    if ns.geometry and not re.fullmatch(r"\d+x\d+", ns.geometry):
        parser.error(f"--geometry must be WxH, got {ns.geometry!r}")
    return Config(
        command=command, wait_for=ns.wait_for, png=ns.png, raw_log=ns.raw_log, mode=ns.mode,
        timeout=ns.timeout, settle=ns.settle, cols=ns.cols, rows=ns.rows, term=ns.term,
        colorterm=None if ns.no_colorterm else ns.colorterm, env=dict(ns.env), text_out=ns.text_out,
        display=ns.display, font=ns.font, geometry=ns.geometry,
    )


def child_env(base: dict[str, str], cfg: Config) -> dict[str, str]:
    """The environment the captured command sees."""
    env = dict(base)
    term = cfg.effective_term
    if term is not None:
        env["TERM"] = term
    if cfg.colorterm is None:
        env.pop("COLORTERM", None)
    else:
        env["COLORTERM"] = cfg.colorterm
    env["COLUMNS"], env["LINES"] = str(cfg.cols), str(cfg.rows)
    env.update(cfg.env)
    return env


def terminator_inner_command(cfg: Config) -> list[str]:
    """What Terminator runs: `env` applies TERM/COLORTERM overrides on top of VTE's, `script`
    records the raw bytes the command writes to the terminal."""
    env_args = ["env"]
    if cfg.colorterm is None:
        env_args += ["-u", "COLORTERM"]
    else:
        env_args.append(f"COLORTERM={cfg.colorterm}")
    if cfg.term is not None:
        env_args.append(f"TERM={cfg.term}")
    env_args += [f"{k}={v}" for k, v in cfg.env.items()]
    inner = shlex.join(env_args + cfg.command)
    return ["script", "-q", "-f", "-e", "-c", inner, str(cfg.raw_log)]


def terminator_config(font: str) -> str:
    return ("[global_config]\n[keybindings]\n[profiles]\n  [[default]]\n"
            f"    use_system_font = False\n    font = {font}\n"
            "    show_titlebar = False\n    scrollbar_position = hidden\n"
            "    scrollback_lines = 0\n    exit_action = hold\n"
            "[layouts]\n[plugins]\n")


def default_geometry(cols: int, rows: int, font: str) -> str:
    """Approximate window pixels for cols x rows at the font's point size (VTE cell ~0.6em x 1.2em @96dpi)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", font)
    pt = float(m.group(1)) if m else 12.0
    px = pt * 96 / 72
    return f"{int(cols * px * 0.62) + 4}x{int(rows * px * 1.2) + 4}"


# --------------------------------------------------------------------------- screen model

class ScreenModel:
    """Raw terminal bytes -> pyte screen (text + per-cell SGR attributes)."""

    def __init__(self, cols: int, rows: int):
        import pyte  # imported lazily so --help works without the dependency
        self.screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self.screen)
        self.raw = bytearray()

    def feed(self, data: bytes) -> None:
        self.raw.extend(data)
        self._stream.feed(data)

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.screen.display)

    def cell(self, x: int, y: int):
        return self.screen.buffer[y][x]


def predicate_met(model: ScreenModel, pattern: re.Pattern) -> bool:
    return pattern.search(model.text()) is not None


def model_from_bytes(data: bytes, cols: int, rows: int) -> ScreenModel:
    m = ScreenModel(cols, rows)
    m.feed(data)
    return m


# --------------------------------------------------------------------------- PNG from a model

CELL_W, CELL_H = 9, 18
DEFAULT_BG, DEFAULT_FG = (18, 18, 24), (220, 220, 220)
NAMED = {"black": (0, 0, 0), "red": (205, 49, 49), "green": (13, 188, 121), "brown": (229, 229, 16),
         "blue": (36, 114, 200), "magenta": (188, 63, 188), "cyan": (17, 168, 205), "white": (229, 229, 229),
         "brightblack": (102, 102, 102), "brightred": (241, 76, 76), "brightgreen": (35, 209, 139),
         "brightbrown": (245, 245, 67), "brightblue": (59, 142, 234), "brightmagenta": (214, 112, 214),
         "brightcyan": (41, 184, 219), "brightwhite": (255, 255, 255)}

# Block elements -> filled rectangles as cell fractions (x0, y0, x1, y1). Drawn as geometry,
# never through the font, which is what VTE and iTerm2 do for this range.
BLOCKS = {
    "█": [(0, 0, 1, 1)], "▀": [(0, 0, 1, .5)], "▄": [(0, .5, 1, 1)], "▌": [(0, 0, .5, 1)], "▐": [(.5, 0, 1, 1)],
    "▖": [(0, .5, .5, 1)], "▗": [(.5, .5, 1, 1)], "▘": [(0, 0, .5, .5)], "▝": [(.5, 0, 1, .5)],
    "▙": [(0, 0, .5, 1), (.5, .5, 1, 1)], "▛": [(0, 0, 1, .5), (0, .5, .5, 1)],
    "▜": [(0, 0, 1, .5), (.5, .5, 1, 1)], "▟": [(.5, 0, 1, 1), (0, .5, .5, 1)],
    "▚": [(0, 0, .5, .5), (.5, .5, 1, 1)], "▞": [(.5, 0, 1, .5), (0, .5, .5, 1)],
}


def resolve_color(value: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    """pyte colour (named, 'default', or 6-hex for 256/24-bit) -> RGB."""
    if value in NAMED:
        return NAMED[value]
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            pass
    return default


def cell_colors(cell) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    fg, bg = resolve_color(cell.fg, DEFAULT_FG), resolve_color(cell.bg, DEFAULT_BG)
    return (bg, fg) if cell.reverse else (fg, bg)


def _load_font(size: int = 14):
    from PIL import ImageFont
    for path in MONO_FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_png(model: ScreenModel, path: Path) -> Path:
    from PIL import Image, ImageDraw
    screen = model.screen
    img = Image.new("RGB", (screen.columns * CELL_W, screen.lines * CELL_H), DEFAULT_BG)
    draw = ImageDraw.Draw(img)
    font = _load_font()
    for y in range(screen.lines):
        row = screen.buffer[y]
        for x in range(screen.columns):
            cell = row[x]
            fg, bg = cell_colors(cell)
            px, py = x * CELL_W, y * CELL_H
            if bg != DEFAULT_BG:
                draw.rectangle([px, py, px + CELL_W - 1, py + CELL_H - 1], fill=bg)
            ch = cell.data
            if ch in BLOCKS:
                for x0, y0, x1, y1 in BLOCKS[ch]:
                    draw.rectangle([px + round(x0 * CELL_W), py + round(y0 * CELL_H),
                                    px + round(x1 * CELL_W) - 1, py + round(y1 * CELL_H) - 1], fill=fg)
            elif ch.strip():
                draw.text((px, py), ch, font=font, fill=fg)
    img.save(path, format="PNG")
    return path


# =========================================================================== I/O shell
# Everything below touches processes, ptys, X displays. Not unit-tested; exercised by
# tools/spikes/12-terminal-rendering-real-tui/demo-capture.sh and the smoke test.

class PredicateTimeout(RuntimeError):
    pass


def _write_outputs(cfg: Config, model: ScreenModel, png: bool = True) -> None:
    cfg.raw_log.write_bytes(bytes(model.raw))
    if cfg.text_out:
        cfg.text_out.write_text(model.text() + "\n", encoding="utf-8")
    if png:
        render_png(model, cfg.png)


def capture_virtual(cfg: Config) -> None:
    import fcntl, pty, select, signal, struct, termios, time

    model = ScreenModel(cfg.cols, cfg.rows)
    env = child_env(os.environ, cfg)
    pid, fd = pty.fork()
    if pid == 0:  # child
        try:
            os.execvpe(cfg.command[0], cfg.command, env)
        except OSError as exc:
            os.write(2, f"capture_tui: cannot exec {cfg.command[0]!r}: {exc}\n".encode())
        os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", cfg.rows, cfg.cols, 0, 0))

    def read_once(wait: float) -> bool:
        """One select+read; False once the child has closed the pty."""
        ready, _, _ = select.select([fd], [], [], wait)
        if not ready:
            return True
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            return False
        if not chunk:
            return False
        model.feed(chunk)
        return True

    try:
        deadline = time.monotonic() + cfg.timeout
        alive, matched = True, False
        while alive and time.monotonic() < deadline:
            alive = read_once(min(0.1, max(0.0, deadline - time.monotonic())))
            if predicate_met(model, cfg.wait_for):
                matched = True
                break
        if not matched:
            _write_outputs(cfg, model, png=False)
            raise PredicateTimeout(f"predicate {cfg.wait_for.pattern!r} not observed within {cfg.timeout}s"
                                   f"{'' if alive else ' (command exited)'}; last screen:\n{model.text()[-800:]}")
        settle_end = time.monotonic() + cfg.settle
        while alive and time.monotonic() < settle_end:
            alive = read_once(min(0.1, max(0.0, settle_end - time.monotonic())))
        _write_outputs(cfg, model)
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
                time.sleep(0.2)
            except OSError:
                break
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
        os.close(fd)


def _xvfb_binary() -> str | None:
    import shutil
    local = Path.home() / ".local/opt/xvfb/root/usr/bin/Xvfb"
    return str(local) if local.exists() else shutil.which("Xvfb")


def _display_running(display: str) -> bool:
    return Path(f"/tmp/.X11-unix/X{display.lstrip(':').split('.')[0]}").exists()


def _screenshot(display: str, out: Path, size: str) -> None:
    import shutil, subprocess
    helper = Path.home() / ".local/opt/xvfb/xvfb-shot.sh"
    if helper.is_file():
        r = subprocess.run(["bash", str(helper), display, str(out), size], capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise RuntimeError(f"xvfb-shot.sh failed: {r.stderr.strip() or r.stdout.strip()}")
        return
    xwd, convert = shutil.which("xwd"), shutil.which("convert")
    if not (xwd and convert):
        raise RuntimeError("terminator mode needs ~/.local/opt/xvfb/xvfb-shot.sh or xwd + ImageMagick convert")
    shot = subprocess.run([xwd, "-root", "-display", display], capture_output=True, timeout=15, check=True)
    subprocess.run([convert, "xwd:-", "-crop", f"{size}+0+0", f"png:{out}"], input=shot.stdout, check=True)


def capture_terminator(cfg: Config) -> None:
    import shutil, subprocess, tempfile, time

    for tool in ("terminator", "dbus-run-session", "script"):
        if not shutil.which(tool):
            raise RuntimeError(f"terminator mode requires `{tool}` on PATH")
    geometry = cfg.geometry or default_geometry(cfg.cols, cfg.rows, cfg.font)
    xvfb_proc = None
    if not _display_running(cfg.display):
        xvfb = _xvfb_binary()
        if not xvfb:
            raise RuntimeError(f"display {cfg.display} not running and no Xvfb found")
        xvfb_proc = subprocess.Popen([xvfb, cfg.display, "-screen", "0", "1920x1200x24", "-nolisten", "tcp"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if _display_running(cfg.display):
                break
            time.sleep(0.1)
    cfgdir = tempfile.mkdtemp(prefix="capture-tui-xdg-")
    (Path(cfgdir) / "terminator").mkdir()
    (Path(cfgdir) / "terminator" / "config").write_text(terminator_config(cfg.font))
    cfg.raw_log.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("TERM", "COLORTERM")}
    env.update(DISPLAY=cfg.display, XDG_CONFIG_HOME=cfgdir)
    term = subprocess.Popen(["dbus-run-session", "--", "terminator", "-u", f"--geometry={geometry}+0+0",
                             "-x", *terminator_inner_command(cfg)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + cfg.timeout
        model = ScreenModel(cfg.cols, cfg.rows)
        matched = False
        while time.monotonic() < deadline:
            time.sleep(0.25)
            data = cfg.raw_log.read_bytes() if cfg.raw_log.exists() else b""
            if len(data) != len(model.raw):
                model = model_from_bytes(data, cfg.cols, cfg.rows)
            if predicate_met(model, cfg.wait_for):
                matched = True
                break
            if term.poll() is not None:
                break
        if not matched:
            if cfg.text_out:
                cfg.text_out.write_text(model.text() + "\n", encoding="utf-8")
            raise PredicateTimeout(f"predicate {cfg.wait_for.pattern!r} not observed on {cfg.display} within "
                                   f"{cfg.timeout}s; last screen:\n{model.text()[-800:]}")
        time.sleep(cfg.settle)
        _screenshot(cfg.display, cfg.png, geometry)
        # the log is script's own file; re-read it so the text dump includes the settle period
        model = model_from_bytes(cfg.raw_log.read_bytes(), cfg.cols, cfg.rows)
        if cfg.text_out:
            cfg.text_out.write_text(model.text() + "\n", encoding="utf-8")
    finally:
        import signal
        try:
            os.killpg(term.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            term.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(term.pid, signal.SIGKILL)
        if xvfb_proc:
            xvfb_proc.terminate()
        shutil.rmtree(cfgdir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    cfg.png.parent.mkdir(parents=True, exist_ok=True)
    cfg.raw_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        (capture_virtual if cfg.mode == "virtual" else capture_terminator)(cfg)
    except PredicateTimeout as exc:
        print(f"capture_tui: TIMEOUT: {exc}", file=sys.stderr)
        return EXIT_TIMEOUT
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"capture_tui: ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"PNG: {cfg.png}\nRAW: {cfg.raw_log}" + (f"\nTEXT: {cfg.text_out}" if cfg.text_out else ""))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
