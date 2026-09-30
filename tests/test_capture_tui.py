"""Pure parts of tools/capture_tui.py: CLI contract, child environment, SGR bytes -> screen
model, predicate matching, PNG rendering from a model. Plus one virtual-backend smoke run
through a real pty (no X), and the exit-code contract on predicate timeout."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import PIL.Image  # hard dependency: a missing Pillow/pyte must fail, never skip
import pyte  # noqa: F401
import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "capture_tui.py"
_spec = importlib.util.spec_from_file_location("capture_tui", TOOL)
ct = importlib.util.module_from_spec(_spec)
sys.modules["capture_tui"] = ct
_spec.loader.exec_module(ct)


def _args(*extra, cmd=("echo", "hi")):
    return ["--wait-for", "hi", "--png", "o.png", "--raw-log", "o.sgr", *extra, "--", *cmd]


# ----------------------------------------------------------------- CLI contract

def test_help_runs_as_a_script():
    r = subprocess.run([sys.executable, str(TOOL), "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    for flag in ("--wait-for", "--png", "--raw-log", "--timeout", "--mode"):
        assert flag in r.stdout


def test_command_after_double_dash_keeps_its_own_flags():
    cfg = ct.parse_args(_args(cmd=("hermes", "--tui", "--wait-for", "x")))
    assert cfg.command == ["hermes", "--tui", "--wait-for", "x"]
    assert cfg.wait_for.pattern == "hi"


def test_defaults():
    cfg = ct.parse_args(_args())
    assert (cfg.mode, cfg.cols, cfg.rows, cfg.timeout) == ("virtual", 100, 24, 15.0)
    assert cfg.colorterm == "truecolor"
    assert cfg.effective_term == "xterm-256color"


@pytest.mark.parametrize("bad", [
    ["--wait-for", "x", "--png", "a", "--raw-log", "b"],                       # no command
    ["--wait-for", "(", "--png", "a", "--raw-log", "b", "--", "true"],         # bad regex
    ["--wait-for", "x", "--png", "a", "--raw-log", "b", "--timeout", "0", "--", "true"],
    ["--wait-for", "x", "--png", "a", "--raw-log", "b", "--env", "NOEQUALS", "--", "true"],
    ["--wait-for", "x", "--png", "a", "--raw-log", "b", "--geometry", "big", "--", "true"],
    ["--png", "a", "--raw-log", "b", "--", "true"],                             # no predicate
])
def test_invalid_arguments_are_usage_errors(bad):
    with pytest.raises(SystemExit) as exc:
        ct.parse_args(bad)
    assert exc.value.code == 2


def test_predicate_is_multiline():
    cfg = ct.parse_args(["--wait-for", "^READY$", "--png", "a", "--raw-log", "b", "--", "true"])
    assert cfg.wait_for.search("booting\nREADY\n")


# ----------------------------------------------------------------- child environment

def test_child_env_sets_term_colorterm_size_and_extras():
    cfg = ct.parse_args(_args("--cols", "80", "--rows", "30", "--env", "A=1", "--env", "B=x=y"))
    env = ct.child_env({"PATH": "/bin", "TERM": "dumb"}, cfg)
    assert env["TERM"] == "xterm-256color" and env["COLORTERM"] == "truecolor"
    assert (env["COLUMNS"], env["LINES"]) == ("80", "30")
    assert env["A"] == "1" and env["B"] == "x=y" and env["PATH"] == "/bin"


def test_child_env_no_colorterm_removes_inherited_value():
    cfg = ct.parse_args(_args("--no-colorterm", "--term", "screen-256color"))
    env = ct.child_env({"COLORTERM": "truecolor"}, cfg)
    assert "COLORTERM" not in env and env["TERM"] == "screen-256color"


def test_terminator_keeps_vte_term_unless_overridden():
    cfg = ct.parse_args(_args("--mode", "terminator"))
    assert cfg.effective_term is None
    inner = ct.terminator_inner_command(cfg)
    assert inner[:2] == ["script", "-q"] and inner[-1] == "o.sgr"
    words = inner[-2].split()
    assert not any(w.startswith("TERM=") for w in words) and "COLORTERM=truecolor" in words


def test_terminator_inner_command_quotes_and_unsets():
    cfg = ct.parse_args(_args("--mode", "terminator", "--no-colorterm", "--term", "xterm",
                              cmd=("sh", "-c", "echo 'a b'; sleep 1")))
    shell = ct.terminator_inner_command(cfg)[-2]
    assert shell.startswith("env -u COLORTERM TERM=xterm sh -c ")
    assert "'echo '\"'\"'a b'\"'\"'; sleep 1'" in shell


def test_terminator_config_sets_font():
    text = ct.terminator_config("Noto Mono 11")
    assert "font = Noto Mono 11" in text and "use_system_font = False" in text


def test_default_geometry_scales_with_grid():
    w1, h1 = map(int, ct.default_geometry(80, 24, "Mono 12").split("x"))
    w2, h2 = map(int, ct.default_geometry(160, 48, "Mono 12").split("x"))
    assert w2 > 1.9 * w1 and h2 > 1.9 * h1


# ----------------------------------------------------------------- screen model + predicate

def test_predicate_matches_rendered_screen_not_raw_bytes():
    # "WAIT" is overwritten in place by "DONE": the byte stream contains both, the screen only one
    m = ct.model_from_bytes(b"WAIT\rDONE", 20, 3)
    assert ct.predicate_met(m, ct._regex("DONE"))
    assert not ct.predicate_met(m, ct._regex("WAIT"))


def test_predicate_sees_text_split_by_sgr():
    m = ct.model_from_bytes(b"\x1b[1;38;2;10;20;30mRE\x1b[0mADY", 20, 3)
    assert ct.predicate_met(m, ct._regex("^READY$"))


def test_predicate_follows_cursor_addressing():
    m = ct.model_from_bytes(b"\x1b[2J\x1b[3;5Hmantle", 20, 5)
    assert m.text().splitlines()[2] == "    mantle"


def test_screen_model_keeps_raw_bytes_verbatim():
    data = b"\x1b[38;2;1;2;3m\xe2\x96\x80\x1b[0m"
    m = ct.ScreenModel(10, 2)
    m.feed(data[:5]); m.feed(data[5:])
    assert bytes(m.raw) == data


def test_truecolor_and_256_sgr_resolve_to_rgb():
    m = ct.model_from_bytes(b"\x1b[38;2;200;100;50;48;5;196m\xe2\x96\x80", 4, 1)
    fg, bg = ct.cell_colors(m.cell(0, 0))
    assert fg == (200, 100, 50)
    assert bg == (255, 0, 0)          # xterm index 196


def test_reverse_video_swaps_colors():
    m = ct.model_from_bytes(b"\x1b[7;31mX", 4, 1)
    fg, bg = ct.cell_colors(m.cell(0, 0))
    assert bg == ct.NAMED["red"] and fg == ct.DEFAULT_BG


def test_resolve_color_falls_back_on_default_and_garbage():
    assert ct.resolve_color("default", (1, 2, 3)) == (1, 2, 3)
    assert ct.resolve_color("zzzzzz", (1, 2, 3)) == (1, 2, 3)


# ----------------------------------------------------------------- PNG rendering

def _render(tmp_path, data, cols=4, rows=1):
    out = ct.render_png(ct.model_from_bytes(data, cols, rows), tmp_path / "s.png")
    return PIL.Image.open(out).convert("RGB")


def test_png_size_is_grid_times_cell(tmp_path):
    img = _render(tmp_path, b"x", cols=7, rows=3)
    assert img.size == (7 * ct.CELL_W, 3 * ct.CELL_H)


def test_upper_half_block_paints_fg_on_top_bg_on_bottom(tmp_path):
    img = _render(tmp_path, b"\x1b[38;2;250;0;0;48;2;0;0;250m\xe2\x96\x80")
    top = img.getpixel((ct.CELL_W // 2, 1))
    bottom = img.getpixel((ct.CELL_W // 2, ct.CELL_H - 2))
    assert top == (250, 0, 0) and bottom == (0, 0, 250)


def test_adjacent_full_blocks_are_seamless(tmp_path):
    img = _render(tmp_path, b"\x1b[38;2;0;200;0m\xe2\x96\x88\xe2\x96\x88", cols=2)
    row = [img.getpixel((x, ct.CELL_H // 2)) for x in range(2 * ct.CELL_W)]
    assert set(row) == {(0, 200, 0)}


def test_quadrant_fills_only_its_quarter(tmp_path):
    img = _render(tmp_path, b"\x1b[38;2;255;255;255m\xe2\x96\x97")      # ▗ lower right
    assert img.getpixel((ct.CELL_W - 1, ct.CELL_H - 1)) == (255, 255, 255)
    assert img.getpixel((0, 0)) == ct.DEFAULT_BG
    assert img.getpixel((0, ct.CELL_H - 1)) == ct.DEFAULT_BG


# ----------------------------------------------------------------- virtual backend (real pty)

def _run(tmp_path, *extra, cmd):
    png, raw = tmp_path / "cap.png", tmp_path / "cap.sgr"
    rc = ct.main(["--png", str(png), "--raw-log", str(raw), "--cols", "40", "--rows", "6",
                  *extra, "--", *cmd])
    return rc, png, raw


def test_virtual_capture_writes_png_and_raw_sgr(tmp_path):
    script = r'printf "\033[38;2;10;200;30m\342\226\200\342\226\200\033[0m READY\n"; sleep 30'
    rc, png, raw = _run(tmp_path, "--wait-for", "READY", "--timeout", "10", "--settle", "0.1",
                        cmd=("sh", "-c", script))
    assert rc == 0
    assert b"\x1b[38;2;10;200;30m" in raw.read_bytes()
    img = PIL.Image.open(png).convert("RGB")
    assert img.size == (40 * ct.CELL_W, 6 * ct.CELL_H)
    assert img.getpixel((ct.CELL_W // 2, 1)) == (10, 200, 30)


def test_virtual_capture_child_sees_term_and_size(tmp_path):
    rc, _, raw = _run(tmp_path, "--wait-for", r"T=\S+ C=\S+ S=6 40", "--timeout", "10", "--no-colorterm",
                      cmd=("sh", "-c", 'echo "T=$TERM C=${COLORTERM:-unset} S=$(stty size)"; sleep 30'))
    assert rc == 0
    assert b"T=xterm-256color C=unset S=6 40" in raw.read_bytes()


def test_virtual_capture_times_out_with_exit_2_and_keeps_log(tmp_path):
    rc, png, raw = _run(tmp_path, "--wait-for", "NEVER", "--timeout", "1",
                        cmd=("sh", "-c", "echo booting; sleep 30"))
    assert rc == ct.EXIT_TIMEOUT
    assert not png.exists()
    assert b"booting" in raw.read_bytes()


def test_virtual_capture_command_exit_before_match_is_timeout(tmp_path):
    rc, _, _ = _run(tmp_path, "--wait-for", "NEVER", "--timeout", "10", cmd=("true",))
    assert rc == ct.EXIT_TIMEOUT
