"""capture_tui.py --sequence: several shots from ONE terminal session, each gated on the program's own
ack of the frame it drew. Real pty runs (virtual backend), behaviour on outputs only."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import PIL.Image
import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "capture_tui.py"
_spec = importlib.util.spec_from_file_location("capture_tui_seq", TOOL)
ct = importlib.util.module_from_spec(_spec)
sys.modules["capture_tui_seq"] = ct
_spec.loader.exec_module(ct)

# A tiny "program under test": redraws the screen from scene.json whenever it changes, then writes
# ack.json {"seq": n} — the same protocol the P1 stub widget speaks.
PROGRAM = r'''
import json, os, sys, time
scene, ack = sys.argv[1], sys.argv[2]
last = None
while True:
    try:
        raw = open(scene).read()
    except OSError:
        raw = None
    if raw and raw != last:
        last = raw
        s = json.loads(raw)
        r, g, b = s["rgb"]
        sys.stdout.write("\x1b[2J\x1b[H\x1b[38;2;%d;%d;%dm\u2580\u2580\u2580\x1b[0m FRAME %s\n" % (r, g, b, s["seq"]))
        sys.stdout.flush()
        tmp = ack + ".tmp"
        open(tmp, "w").write(json.dumps({"seq": s["seq"], "pid": os.getpid()}))
        os.replace(tmp, ack)
    time.sleep(0.05)
'''


def _run(tmp_path, steps, first_seq=0):
    prog = tmp_path / "prog.py"
    prog.write_text(PROGRAM)
    scene, ack = tmp_path / "scene.json", tmp_path / "ack.json"
    scene.write_text(json.dumps({"seq": first_seq, "rgb": [1, 2, 3]}))
    seq = tmp_path / "seq.json"
    seq.write_text(json.dumps(steps(scene, ack)))
    cmd = [sys.executable, str(TOOL), "--wait-for", f"FRAME {first_seq}", "--timeout", "15", "--settle", "0.1",
           "--cols", "30", "--rows", "4", "--png", str(tmp_path / "first.png"), "--raw-log", str(tmp_path / "first.sgr"),
           "--sequence", str(seq), "--", sys.executable, str(prog), str(scene), str(ack)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def test_sequence_takes_one_shot_per_step_each_showing_its_own_scene(tmp_path):
    colours = [(200, 10, 10), (10, 200, 10), (10, 10, 200)]

    def steps(scene, ack):
        return [{"png": str(tmp_path / f"s{i}.png"), "text_out": str(tmp_path / f"s{i}.txt"),
                 "ps_log": str(tmp_path / f"s{i}.ps"), "ack_out": str(tmp_path / f"s{i}.ack"),
                 "write": {"path": str(scene), "text": json.dumps({"seq": i + 1, "rgb": c})},
                 "ack": {"path": str(ack), "seq": i + 1}, "wait_for": "FRAME", "settle": 0.1}
                for i, c in enumerate(colours)]

    r = _run(tmp_path, steps)
    assert r.returncode == 0, r.stderr
    pids = set()
    for i, c in enumerate(colours):
        img = PIL.Image.open(tmp_path / f"s{i}.png").convert("RGB")
        assert img.getpixel((ct.CELL_W // 2, 1)) == c          # the ▀ top half carries THIS step's colour
        assert f"FRAME {i + 1}" in (tmp_path / f"s{i}.txt").read_text()
        ack = json.loads((tmp_path / f"s{i}.ack").read_text())
        assert ack["seq"] == i + 1
        ps = (tmp_path / f"s{i}.ps").read_text()
        # the process list at capture names the program that acked the frame, and it was alive
        assert any(line.split()[0] == str(ack["pid"]) and "prog.py" in line for line in ps.splitlines()[1:])
        pids.add(ack["pid"])
    assert len(pids) == 1                                      # ONE session served every shot


def test_sequence_step_whose_ack_never_arrives_is_a_timeout(tmp_path):
    def steps(scene, ack):
        # The program acks seq 1, but the step waits for seq 99: the capture must not take the stale frame.
        return [{"png": str(tmp_path / "s0.png"), "write": {"path": str(scene), "text": json.dumps({"seq": 1, "rgb": [9, 9, 9]})},
                 "ack": {"path": str(ack), "seq": 99}, "timeout": 2}]

    r = _run(tmp_path, steps)
    assert r.returncode == ct.EXIT_TIMEOUT
    assert not (tmp_path / "s0.png").exists()
    assert "ack seq 99" in r.stderr


@pytest.mark.parametrize("bad", [[], [{}], [{"png": "a.png", "write": {"path": "x"}}],
                                 [{"png": "a.png", "ack": {"path": "x"}}], "nope"])
def test_bad_sequence_is_a_usage_error(tmp_path, bad):
    seq = tmp_path / "seq.json"
    seq.write_text(json.dumps(bad))
    r = subprocess.run([sys.executable, str(TOOL), "--wait-for", "x", "--png", "a.png", "--raw-log", "a.sgr",
                        "--sequence", str(seq), "--", "true"], capture_output=True, text=True)
    assert r.returncode == 2
    assert f"--sequence {seq}:" in r.stderr          # the tool names the file and the reason, not argparse's "unrecognized"


def test_terminator_profile_never_dims_the_palette():
    # Terminator multiplies PALETTE colours (the 256 rung) of an unfocused terminal by
    # inactive_color_offset (default 0.8); a WM-less Xvfb never focuses the window. Measured:
    # #875faf rendered as (108, 76, 140) before this setting.
    text = ct.terminator_config("DejaVu Sans Mono 13")
    glob = text.split("[keybindings]")[0]
    assert "inactive_color_offset = 1.0" in glob
