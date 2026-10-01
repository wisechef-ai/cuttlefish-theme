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
    actual_grid: tuple[int, int] | None = None   # set by the backend: the grid the terminal really had
    sequence: list["Step"] | None = None       # --sequence: several shots from ONE terminal session

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
    p.add_argument("--sequence", type=Path, metavar="STEPS.json",
                   help="after the first --wait-for match, run these steps in the SAME terminal session, one "
                        "screenshot each (see Step); --png/--raw-log still get the first frame")
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
        sequence=load_sequence(ns.sequence, parser) if ns.sequence else None,
    )


@dataclass
class Step:
    """One shot of a --sequence run. Order: write `write_text` to `write_path` (tmp + rename, so a
    watcher never reads half a file), then wait until the screen matches `wait_for` (default: the
    run's --wait-for) AND, when `ack_path` is set, that JSON file has `"seq": ack_seq` (the program
    under test confirms it drew the frame we asked for), then `settle`, then capture."""
    png: Path
    raw_log: Path | None = None
    text_out: Path | None = None
    write_path: Path | None = None
    write_text: str | None = None
    wait_for: re.Pattern | None = None
    ack_path: Path | None = None
    ack_seq: object = None
    settle: float | None = None
    timeout: float | None = None
    ps_log: Path | None = None
    ack_out: Path | None = None
    stable: re.Pattern | None = None


def layout_signature(model: "ScreenModel", pattern: re.Pattern | None) -> tuple:
    """Rows (index, text) that match `pattern`: equal before and after a screenshot means the screen did not
    move under the shot. A real terminal repaints asynchronously, so the screen-model snapshot and the pixels
    can disagree by one frame (measured: a boot status line vanished between them and every crop was off by
    one row)."""
    if pattern is None:
        return ()
    return tuple((y, line) for y, line in enumerate(model.text().split("\n")) if pattern.search(line))


def parse_sequence(items: list) -> list[Step]:
    """JSON list -> steps. Raises ValueError naming the bad step."""
    if not isinstance(items, list) or not items:
        raise ValueError("sequence must be a non-empty JSON list")
    steps = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("png"):
            raise ValueError(f"step {i}: needs at least {{\"png\": path}}")
        write, ack = it.get("write") or {}, it.get("ack") or {}
        if write and not ("path" in write and "text" in write):
            raise ValueError(f"step {i}: write needs path + text")
        if ack and not ("path" in ack and "seq" in ack):
            raise ValueError(f"step {i}: ack needs path + seq")
        try:
            pattern = re.compile(it["wait_for"], re.MULTILINE) if it.get("wait_for") else None
        except re.error as exc:
            raise ValueError(f"step {i}: bad wait_for: {exc}") from exc
        steps.append(Step(
            png=Path(it["png"]), raw_log=Path(it["raw_log"]) if it.get("raw_log") else None,
            text_out=Path(it["text_out"]) if it.get("text_out") else None,
            write_path=Path(write["path"]) if write else None, write_text=write.get("text") if write else None,
            wait_for=pattern, ack_path=Path(ack["path"]) if ack else None, ack_seq=ack.get("seq") if ack else None,
            settle=float(it["settle"]) if it.get("settle") is not None else None,
            timeout=float(it["timeout"]) if it.get("timeout") is not None else None,
            ps_log=Path(it["ps_log"]) if it.get("ps_log") else None,
            ack_out=Path(it["ack_out"]) if it.get("ack_out") else None,
            stable=re.compile(it["stable"]) if it.get("stable") else None,
        ))
    return steps


def load_sequence(path: Path, parser: argparse.ArgumentParser) -> list[Step]:
    import json
    try:
        return parse_sequence(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        parser.error(f"--sequence {path}: {exc}")
        raise  # unreachable; parser.error exits


def ack_satisfied(path: Path | None, seq: object) -> bool:
    """True when there is no ack to wait for, or the ack file is JSON carrying this seq."""
    if path is None:
        return True
    import json
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("seq") == seq
    except (OSError, ValueError, AttributeError):
        return False


def descendants(ps_rows: list[tuple[int, int, str]], root: int) -> list[tuple[int, int, str]]:
    """(pid, ppid, rest) rows -> root and every descendant, in tree order."""
    kids: dict[int, list] = {}
    for row in ps_rows:
        kids.setdefault(row[1], []).append(row)
    out = [r for r in ps_rows if r[0] == root]
    i = 0
    while i < len(out):
        out.extend(sorted(kids.get(out[i][0], []), key=lambda r: r[0]))
        i += 1
    return out


def process_tree_text(root: int) -> str:
    """`ps` of the launched command and everything under it, at this instant (the capture's proof
    of which processes were alive when the frame was taken)."""
    import subprocess
    # -ww: never truncate args (procps cuts them at $COLUMNS/80 otherwise; CI temp paths are long)
    r = subprocess.run(["ps", "-ww", "-e", "-o", "pid=,ppid=,etimes=,args="], capture_output=True, text=True)
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), " ".join(parts[2:])))
    return "PID PPID ELAPSED_S ARGS\n" + "\n".join(f"{p} {pp} {rest}" for p, pp, rest in descendants(rows, root)) + "\n"


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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


def terminator_inner_command(cfg: Config, script_log: Path) -> list[str]:
    """What Terminator runs: `env` applies TERM/COLORTERM overrides on top of VTE's, `script`
    records the raw bytes the command writes to the terminal (into `script_log`, which carries
    script's own header/trailer; parse_script_log strips them)."""
    env_args = ["env"]
    if cfg.colorterm is None:
        env_args += ["-u", "COLORTERM"]
    else:
        env_args.append(f"COLORTERM={cfg.colorterm}")
    if cfg.term is not None:
        env_args.append(f"TERM={cfg.term}")
    env_args += [f"{k}={v}" for k, v in cfg.env.items()]
    inner = shlex.join(env_args + cfg.command)
    return ["script", "-q", "-f", "-e", "-c", inner, str(script_log)]


def terminator_config(font: str) -> str:
    # inactive_color_offset: Terminator dims the PALETTE (indexed colours, i.e. the whole 256 rung) of an
    # unfocused terminal by 0.8, while truecolor SGR bypasses the palette. On a WM-less Xvfb the window is
    # never focused, so without this every 256-colour capture came out at 0.8x (#875faf -> 108,76,140).
    return ("[global_config]\n  inactive_color_offset = 1.0\n[keybindings]\n[profiles]\n  [[default]]\n"
            f"    use_system_font = False\n    font = {font}\n"
            "    show_titlebar = False\n    scrollbar_position = hidden\n"
            "    scrollback_lines = 0\n    exit_action = hold\n"
            "[layouts]\n[plugins]\n")


def default_geometry(cols: int, rows: int, font: str) -> str:
    """Window pixels for cols x rows. Calibrated on Terminator/VTE 0.76 with DejaVu Sans Mono 14 on
    Xvfb (96 dpi): cell ~11.05 x 20 px, ~120 px of fixed vertical chrome (measured: 1330x860 -> 120x37,
    1338x900 -> 121x39). Cell size scales with point size. Other fonts differ, so this is only an
    estimate: the real grid is read back from script(1)'s log header and reported (see
    parse_script_log); pass --geometry to pin it."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", font)
    scale = (float(m.group(1)) if m else 14.0) / 14.0
    return f"{round(cols * 11.05 * scale) + 6}x{round(rows * 20 * scale) + 128}"


def corrected_geometry(geometry: str, want: tuple[int, int], got: tuple[int, int], font: str) -> str:
    """Next window size to try: shift by the cell delta between the grid we got and the one we want."""
    w, h = map(int, geometry.split("x"))
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", font)
    scale = (float(m.group(1)) if m else 14.0) / 14.0
    return f"{w + round((want[0] - got[0]) * 11.05 * scale)}x{h + round((want[1] - got[1]) * 20 * scale)}"


_SCRIPT_HEADER = re.compile(rb"\AScript started on [^\n]*?\[(?P<meta>[^\n]*)\]\r?\n")
_SCRIPT_TRAILER = re.compile(rb"\r?\nScript done on [^\n]*\[[^\n]*\]\r?\n?\Z")
_SCRIPT_DIM = re.compile(rb'\b(COLUMNS|LINES)="(\d+)"')


def parse_script_log(data: bytes) -> tuple[bytes, tuple[int, int] | None]:
    """util-linux script(1) log -> (terminal bytes only, (cols, rows) of the real pty or None).

    script writes `Script started on DATE [COMMAND=".." TERM=".." TTY=".." COLUMNS="c" LINES="r"]`
    before the payload and `Script done on ...` after it; neither was ever on the screen."""
    dims = None
    head = _SCRIPT_HEADER.match(data)
    if head:
        found = dict(_SCRIPT_DIM.findall(head.group("meta")))
        if b"COLUMNS" in found and b"LINES" in found:
            dims = (int(found[b"COLUMNS"]), int(found[b"LINES"]))
        data = data[head.end():]
    return _SCRIPT_TRAILER.sub(b"", data), dims


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


def run_steps(cfg: Config, pump, current_model, shoot, root_pid: int | None = None) -> None:
    """Drive cfg.sequence against a live terminal. `pump(wait)` reads output (False once the program
    is gone), `current_model()` returns the up-to-date ScreenModel, `shoot(png)` writes the screenshot."""
    import time
    for i, step in enumerate(cfg.sequence or []):
        if step.write_path is not None:
            write_atomic(step.write_path, step.write_text or "")
        pattern = step.wait_for or cfg.wait_for
        deadline = time.monotonic() + (step.timeout or cfg.timeout)
        alive, ok = True, False
        while alive and time.monotonic() < deadline:
            alive = pump(min(0.25, max(0.0, deadline - time.monotonic())))
            if predicate_met(current_model(), pattern) and ack_satisfied(step.ack_path, step.ack_seq):
                ok = True
                break
        if not ok:
            raise PredicateTimeout(f"sequence step {i} ({step.png.name}): {pattern.pattern!r}"
                                   f"{' + ack seq ' + repr(step.ack_seq) if step.ack_path else ''} not observed"
                                   f"{'' if alive else ' (command exited)'}; last screen:\n{current_model().text()[-800:]}")
        settle_end = time.monotonic() + (cfg.settle if step.settle is None else step.settle)
        while alive and time.monotonic() < settle_end:
            alive = pump(min(0.1, max(0.0, settle_end - time.monotonic())))
        step.png.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(6):
            before = layout_signature(current_model(), step.stable)
            if step.ps_log and root_pid:
                step.ps_log.parent.mkdir(parents=True, exist_ok=True)
                step.ps_log.write_text(process_tree_text(root_pid), encoding="utf-8")
            shoot(step.png)
            alive = pump(0.05)
            if layout_signature(current_model(), step.stable) == before:
                break
            print(f"STEP {i}: layout moved during the shot, retaking ({attempt + 1})", file=sys.stderr, flush=True)
            alive = pump(0.4)
        else:
            raise PredicateTimeout(f"sequence step {i} ({step.png.name}): layout never settled for a shot")
        if step.ack_out and step.ack_path:
            step.ack_out.parent.mkdir(parents=True, exist_ok=True)
            step.ack_out.write_bytes(Path(step.ack_path).read_bytes())
        model = current_model()
        if step.raw_log:
            step.raw_log.parent.mkdir(parents=True, exist_ok=True)
            step.raw_log.write_bytes(bytes(model.raw))
        if step.text_out:
            step.text_out.parent.mkdir(parents=True, exist_ok=True)
            step.text_out.write_text(model.text() + "\n", encoding="utf-8")
        print(f"STEP {i}: {step.png}", flush=True)


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
        if cfg.sequence:
            run_steps(cfg, read_once, lambda: model, lambda png: render_png(model, png), root_pid=pid)
    finally:
        # pty.fork() makes the child a session + process-group leader: signal the whole group so
        # grandchildren (the TUI's tui_gateway python, node workers) never outlive the capture.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
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


def _probe_grid(geometry: str, env: dict[str, str], log: Path) -> tuple[int, int] | None:
    """Open Terminator at `geometry` just long enough for script(1) to log the pty size. (script
    only flushes its header together with the first output, hence the `echo`.)"""
    import signal, subprocess, time
    log.unlink(missing_ok=True)
    proc = subprocess.Popen(["dbus-run-session", "--", "terminator", "-u", f"--geometry={geometry}+0+0",
                             "-x", "script", "-q", "-f", "-c", "echo; sleep 5", str(log)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(100):
            time.sleep(0.1)
            if log.exists():
                dims = parse_script_log(log.read_bytes())[1]
                if dims:
                    return dims
        return None
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()


def _calibrate_geometry(cfg: Config, geometry: str, env: dict[str, str], log: Path) -> str:
    """Closed loop: VTE's window chrome and minimum size vary, so measure instead of trusting a formula."""
    want = (cfg.cols, cfg.rows)
    got = None
    for _ in range(4):
        got = _probe_grid(geometry, env, log)
        if got is None or got == want:
            break
        geometry = corrected_geometry(geometry, want, got, cfg.font)
    if got != want:
        raise RuntimeError(f"Terminator cannot show a {want[0]}x{want[1]} grid on {cfg.display} with font "
                           f"{cfg.font!r} (last probe {geometry} -> {got}); the screen may be too small, or "
                           f"pass --geometry explicitly")
    return geometry


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
    try:
        _run_terminator(cfg, geometry, Path(cfgdir))
    finally:
        if xvfb_proc:
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=5)
        shutil.rmtree(cfgdir, ignore_errors=True)


def _run_terminator(cfg: Config, geometry: str, cfgdir: Path) -> None:
    import signal, subprocess, time

    (cfgdir / "terminator").mkdir()
    (cfgdir / "terminator" / "config").write_text(terminator_config(cfg.font))
    script_log = cfgdir / "script.log"
    env = {k: v for k, v in os.environ.items() if k not in ("TERM", "COLORTERM", "COLUMNS", "LINES")}
    env.update(DISPLAY=cfg.display, XDG_CONFIG_HOME=str(cfgdir))
    if not cfg.geometry:
        geometry = _calibrate_geometry(cfg, geometry, env, cfgdir / "probe.log")
    term = subprocess.Popen(["dbus-run-session", "--", "terminator", "-u", f"--geometry={geometry}+0+0",
                             "-x", *terminator_inner_command(cfg, script_log)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def snapshot() -> tuple[bytes, ScreenModel]:
        payload, dims = parse_script_log(script_log.read_bytes() if script_log.exists() else b"")
        cols, rows = dims or (cfg.cols, cfg.rows)
        return payload, model_from_bytes(payload, cols, rows)

    try:
        deadline = time.monotonic() + cfg.timeout
        payload, model = snapshot()
        matched = False
        while time.monotonic() < deadline:
            time.sleep(0.25)
            payload, model = snapshot()
            if predicate_met(model, cfg.wait_for):
                matched = True
                break
            if term.poll() is not None:
                break
        if not matched:
            cfg.raw_log.write_bytes(payload)
            if cfg.text_out:
                cfg.text_out.write_text(model.text() + "\n", encoding="utf-8")
            raise PredicateTimeout(f"predicate {cfg.wait_for.pattern!r} not observed on {cfg.display} within "
                                   f"{cfg.timeout}s; last screen:\n{model.text()[-800:]}")
        time.sleep(cfg.settle)
        _screenshot(cfg.display, cfg.png, geometry)
        payload, model = snapshot()   # include the settle period
        cfg.raw_log.write_bytes(payload)
        grid = (model.screen.columns, model.screen.lines)
        cfg.actual_grid = grid
        if grid != (cfg.cols, cfg.rows):
            print(f"capture_tui: WARNING: Terminator gave a {grid[0]}x{grid[1]} grid, asked for "
                  f"{cfg.cols}x{cfg.rows}; pass --geometry to adjust", file=sys.stderr)
        if cfg.text_out:
            cfg.text_out.write_text(model.text() + "\n", encoding="utf-8")
        if cfg.sequence:
            latest = {"model": model}

            def pump(wait: float) -> bool:
                time.sleep(wait)
                latest["model"] = snapshot()[1]
                return term.poll() is None

            def current() -> ScreenModel:
                return latest["model"]

            run_steps(cfg, pump, current, lambda png: _screenshot(cfg.display, png, geometry), root_pid=term.pid)
    finally:
        try:
            os.killpg(term.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            term.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(term.pid, signal.SIGKILL)
            term.wait()


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
    cols, rows = cfg.actual_grid or (cfg.cols, cfg.rows)
    print(f"PNG: {cfg.png}\nRAW: {cfg.raw_log}" + (f"\nTEXT: {cfg.text_out}" if cfg.text_out else "")
          + f"\nGRID: {cols}x{rows}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
