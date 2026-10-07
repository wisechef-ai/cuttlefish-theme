"""check_manifest on synthetic DESKTOP manifests (round 2: D-R2-2 swatch motion, D-R2-3 XL paint size).

Behaviour only: every assertion is on the checker's verdict about files a harness would have written."""
import json
import subprocess
import sys
from pathlib import Path

import PIL.Image

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tools" / "p1" / "check_manifest.py"
STATES = ("idle", "working", "review", "needs-you", "fault", "unknown")
SIZE = (24, 16)


def check(manifest: Path):
    r = subprocess.run([sys.executable, str(CHECK), str(manifest), "--hosts", "desktop"], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


def _png(path: Path, colour):
    path.parent.mkdir(parents=True, exist_ok=True)
    PIL.Image.new("RGB", SIZE, colour).save(path)


def _log(root: Path, name: str):
    p = root / "logs" / f"{name}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("command: node desktop-capture.ts\nhermes_sha: abcdef12345\nplugin_sha: 1234567890a\n"
                 "hermes_home: /tmp/cf-p1h-desk-x\nps (host process tree at capture):\nPID PPID ELAPSED_S ARGS\n"
                 "4242 1 5 /opt/electron/electron --no-sandbox /x/apps/desktop\n")
    return f"logs/{name}.log"


def make_manifest(root: Path, swatch_working_colours=(0, 1, 2, 3), xl_paint=(180, 100)) -> Path:
    """A minimal manifest satisfying the desktop part of the matrix. `swatch_working_colours[i]` is the
    pixel colour index of the S working frame at t = (0, .25, .5, .75)[i]."""
    entries = []

    def add(name, scale, state, deg, t, colour, view_sessions, **extra):
        f = f"desktop/{name}.png"
        _png(root / f, (colour * 40, 60, 60))
        entries.append(dict(file=f, host="desktop", scale=scale, state=state, degraded=deg, rung="dom", depth="truecolor",
                            cols=None, session_idx=1, sessions=view_sessions, frame_t=t, crop=[0, 0, *SIZE],
                            capture_log=_log(root, name), **extra))

    for st, deg in [(s, False) for s in STATES] + [("unknown", True)]:
        for scale in ("XL", "M", "S"):
            for i, t in enumerate((0, .25, .5, .75) if st == "working" else (0, .5)):
                colour = 9 if st != "working" else (swatch_working_colours[i] if scale == "S" else i)
                extra = dict(xl_paint=list(xl_paint)) if scale == "XL" else {}
                add(f"{scale}-{st}-{deg}-{t}", scale, st, deg, t, colour, [] if deg else [1], **extra)
    for t in (0, .5):
        add(f"sidebar-{t}", "S", "idle", False, t, 9, list(range(20)))
    m = {"schema": "cf2909.p1.manifest/1", "direction": "x", "hermes_sha": "abcdef12345", "plugin_sha": "1234567890a",
         "hosts": ["desktop"], "entries": entries}
    (root / "manifest.json").write_text(json.dumps(m))
    return root / "manifest.json"


def test_swatch_with_four_distinct_frames_passes(tmp_path):
    rc, rep = check(make_manifest(tmp_path))
    assert rc == 0, rep


def test_swatch_with_three_distinct_frames_passes(tmp_path):
    rc, rep = check(make_manifest(tmp_path, swatch_working_colours=(0, 1, 2, 1)))
    assert rc == 0, rep


def test_swatch_with_two_distinct_frames_fails(tmp_path):
    rc, rep = check(make_manifest(tmp_path, swatch_working_colours=(0, 1, 0, 1)))
    assert rc == 1
    assert any("need >= 3" in f for f in rep["fails"]["working"]), rep


def test_swatch_with_no_motion_still_fails(tmp_path):
    rc, rep = check(make_manifest(tmp_path, swatch_working_colours=(1, 1, 1, 1)))
    assert rc == 1 and rep["fails"]["working"]


def test_chip_and_field_keep_the_two_frame_rule(tmp_path):
    """Only the 4x2 swatch needs three frames; XL/M working frames are fine with motion at all (checked via 4 distinct above)."""
    rc, rep = check(make_manifest(tmp_path))
    assert rc == 0 and "working" not in rep["fails"]


def test_xl_painted_over_budget_fails(tmp_path):
    rc, rep = check(make_manifest(tmp_path, xl_paint=(400, 300)))
    assert rc == 1 and any("57600" in f for f in rep["fails"]["xl_paint"]), rep


def test_xl_without_a_recorded_paint_size_fails(tmp_path):
    def strip(path):
        m = json.loads(path.read_text())
        for e in m["entries"]:
            e.pop("xl_paint", None)
        path.write_text(json.dumps(m))
    p = make_manifest(tmp_path)
    strip(p)
    rc, rep = check(p)
    assert rc == 1 and rep["fails"]["xl_paint"]


def test_xl_at_exactly_the_budget_passes(tmp_path):
    rc, rep = check(make_manifest(tmp_path, xl_paint=(320, 180)))
    assert rc == 0, rep
