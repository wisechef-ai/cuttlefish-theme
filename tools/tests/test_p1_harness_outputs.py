"""Behaviour tests on P1 harness OUTPUTS (tools/p1/capture_matrix.py → manifest.json, checked by
tools/p1/check_manifest.py). No source reading: every assertion is about files the harness wrote.

Two layers:
  * check_manifest on synthetic manifests — the checker must catch each failure class it claims to catch;
  * an END-TO-END run of capture_matrix through the REAL `hermes --tui` (virtual pty backend) against the
    reference direction, then check_manifest on what it wrote. That needs a built hermes TUI: set
    CF_HERMES_SRC to a hermes-agent checkout with ui-tui/dist/entry.js (CI builds upstream's). Without one the
    end-to-end test FAILS rather than skips, unless CF_P1_ALLOW_NO_TUI=1 (explicit local opt-out).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import PIL.Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tools" / "p1" / "check_manifest.py"
MATRIX = ROOT / "tools" / "p1" / "capture_matrix.py"
REF = ROOT / "design" / "directions" / "_ref"


def check(manifest: Path, hosts="tui"):
    r = subprocess.run([sys.executable, str(CHECK), str(manifest), "--hosts", hosts], capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


# ------------------------------------------------------------------ synthetic manifests

STATES = ("idle", "working", "review", "needs-you", "fault", "unknown")


def _png(path: Path, colour, size=(40, 20)):
    path.parent.mkdir(parents=True, exist_ok=True)
    PIL.Image.new("RGB", size, colour).save(path)


def _log(root: Path, name: str, *, pid=4242, sha="abcdef12345", home="/tmp/cf-p1h-tui-x", proc=None):
    proc = proc or f"/usr/bin/node --expose-gc /x/ui-tui/dist/entry.js"
    p = root / "logs" / f"{name}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"command: python capture_tui.py ...\nhermes_sha: {sha}\nplugin_sha: 1234567890a\nhermes_home: {home}\n"
                 f"ack: {json.dumps({'seq': 1, 'pid': pid})}\nps (host process tree at capture):\nPID PPID ELAPSED_S ARGS\n"
                 f"{pid} 1 5 {proc}\n")
    return f"logs/{name}.log"


def make_manifest(root: Path, mutate=None) -> Path:
    """A minimal manifest that satisfies the TUI part of the matrix."""
    entries = []
    looks = [(s, False) for s in STATES] + [("unknown", True)]

    def add(name, **kw):
        f = f"tui/{name}.png"
        working = kw["state"] == "working"
        colour = (int(kw["frame_t"] * 200), 50, 50) if working else (10, 20, 30)
        _png(root / f, colour)
        entries.append(dict(file=f, host="tui-terminator", rung="half", crop=[0, 0, 40, 20],
                            capture_log=_log(root, name), session_idx=1, **kw))

    for depth, cols in (("truecolor", 120), ("256", 120), ("truecolor", 80)):
        for st, deg in looks:
            for t in ((0, .25, .5, .75) if st == "working" else (0, .5)):
                add(f"M-{depth}-{cols}-{st}-{deg}-{t}", scale="M", state=st, degraded=deg, depth=depth, cols=cols,
                    sessions=[] if deg else [1], frame_t=t)
    for st in STATES:
        for t in ((0, .25, .5, .75) if st == "working" else (0, .5)):
            add(f"S-pill-{st}-{t}", scale="S", state=st, degraded=False, depth="truecolor", cols=120, sessions=[1], frame_t=t)
    for n in (16, 20):
        for t in (0, .5):
            add(f"S-grid{n}-{t}", scale="S", state="idle", degraded=False, depth="truecolor", cols=120,
                sessions=list(range(n)), frame_t=t)
    m = {"schema": "cf2909.p1.manifest/1", "direction": "x", "hermes_sha": "abcdef12345", "plugin_sha": "1234567890a",
         "hosts": ["tui"], "entries": entries}
    if mutate:
        mutate(m, root)
    (root / "manifest.json").write_text(json.dumps(m))
    return root / "manifest.json"


def test_complete_manifest_passes(tmp_path):
    rc, rep = check(make_manifest(tmp_path))
    assert rc == 0, rep
    assert rep["fails"] == {}


def test_wrong_schema_id_fails(tmp_path):
    rc, rep = check(make_manifest(tmp_path, lambda m, r: m.update(schema="other/1")))
    assert rc == 1 and "schema" in rep["fails"]


def test_entry_without_crop_fails_schema(tmp_path):
    rc, rep = check(make_manifest(tmp_path, lambda m, r: m["entries"][0].pop("crop")))
    assert rc == 1 and any("crop" in f for f in rep["fails"]["schema"])


def test_missing_matrix_cell_fails(tmp_path):
    def drop(m, r):
        m["entries"] = [e for e in m["entries"] if not (e["depth"] == "256" and e["state"] == "fault")]
    rc, rep = check(make_manifest(tmp_path, drop))
    assert rc == 1
    assert any("fault" in f and "256" in f for f in rep["fails"]["matrix"])


def test_static_state_whose_frames_differ_fails(tmp_path):
    def flicker(m, r):
        e = next(e for e in m["entries"] if e["state"] == "idle" and e["frame_t"] == .5 and e["scale"] == "M")
        _png(r / e["file"], (99, 99, 99))
    rc, rep = check(make_manifest(tmp_path, flicker))
    assert rc == 1 and rep["fails"]["static"]


def test_working_without_motion_fails(tmp_path):
    def freeze(m, r):
        for e in m["entries"]:
            if e["state"] == "working":
                _png(r / e["file"], (1, 1, 1))
    rc, rep = check(make_manifest(tmp_path, freeze))
    assert rc == 1 and rep["fails"]["working"]


def test_static_proof_only_looks_inside_the_crop(tmp_path):
    # A clock in the status bar changes between frames; the painted box (the crop) does not.
    def clock(m, r):
        for e in m["entries"]:
            if e["state"] == "idle" and e["frame_t"] == .5:
                im = PIL.Image.new("RGB", (40, 30), (10, 20, 30))
                im.putpixel((5, 25), (255, 255, 255))
                im.save(r / e["file"])
    rc, rep = check(make_manifest(tmp_path, clock))
    assert rc == 0, rep


def test_capture_log_without_a_hermes_process_fails(tmp_path):
    def fake(m, r):
        e = m["entries"][3]
        e["capture_log"] = _log(r, "fake", proc="python3 render_preview.py")
    rc, rep = check(make_manifest(tmp_path, fake))
    assert rc == 1 and any("TUI" in f or "process" in f for f in rep["fails"]["capture_log"])


def test_capture_log_whose_ack_pid_is_not_the_tui_fails(tmp_path):
    def other(m, r):
        e = m["entries"][5]
        p = r / e["capture_log"]
        p.write_text(p.read_text().replace('"pid": 4242', '"pid": 999'))
    rc, rep = check(make_manifest(tmp_path, other))
    assert rc == 1 and any("ack pid 999" in f for f in rep["fails"]["capture_log"])


def test_capture_log_against_the_live_home_fails(tmp_path):
    def live(m, r):
        m["entries"][0]["capture_log"] = _log(r, "live", home="/home/adam/.hermes")
    rc, rep = check(make_manifest(tmp_path, live))
    assert rc == 1 and any("throwaway" in f for f in rep["fails"]["capture_log"])


def test_capture_log_with_another_sha_fails(tmp_path):
    def stale(m, r):
        m["entries"][0]["capture_log"] = _log(r, "stale", sha="0000000aaaa")
    rc, rep = check(make_manifest(tmp_path, stale))
    assert rc == 1 and any("hermes_sha" in f for f in rep["fails"]["capture_log"])


# ------------------------------------------------------------------ end to end through the real TUI

def _hermes_src():
    src = os.environ.get("CF_HERMES_SRC")
    if src and (Path(src) / "ui-tui" / "dist" / "entry.js").exists():
        return src
    if os.environ.get("CF_P1_ALLOW_NO_TUI") == "1":
        pytest.skip("CF_P1_ALLOW_NO_TUI=1: no built hermes TUI (set CF_HERMES_SRC)")
    pytest.fail("set CF_HERMES_SRC to a hermes-agent checkout with a built ui-tui/dist/entry.js")


@pytest.fixture(scope="module")
def ref_run(tmp_path_factory):
    src = _hermes_src()
    out = tmp_path_factory.mktemp("renders")
    r = subprocess.run([sys.executable, str(MATRIX), "--direction", str(REF), "--out", str(out), "--backend", "virtual",
                        "--runtime", src], capture_output=True, text=True, timeout=900,
                       env={**os.environ, "HOME": os.environ.get("HOME", "/tmp")})
    return r, out / "_ref"


def test_e2e_matrix_is_complete_and_valid(ref_run):
    r, d = ref_run
    assert r.returncode == 0, r.stderr[-3000:]
    rc, rep = check(d / "manifest.json", "tui")
    assert rc == 0, json.dumps(rep, indent=1)[:3000]
    m = json.loads((d / "manifest.json").read_text())
    assert m["missing"] == []
    assert len(m["entries"]) == 66


def test_e2e_non_working_frames_are_byte_identical(ref_run):
    _, d = ref_run
    m = json.loads((d / "manifest.json").read_text())
    groups = {}
    for e in m["entries"]:
        k = (e["scale"], e["state"], e["degraded"], e["depth"], e["cols"], len(e["sessions"]))
        im = PIL.Image.open(d / e["file"]).convert("RGB")
        x, y, w, h = e["crop"]
        groups.setdefault(k, set()).add(hashlib.sha256(im.crop((x, y, x + w, y + h)).tobytes()).hexdigest())
    for k, hashes in groups.items():
        assert (len(hashes) > 1) == (k[1] == "working"), k


def test_e2e_every_capture_log_names_the_tui_process_that_acked(ref_run):
    _, d = ref_run
    m = json.loads((d / "manifest.json").read_text())
    for e in m["entries"]:
        text = (d / e["capture_log"]).read_text()
        ack = json.loads(next(l for l in text.splitlines() if l.startswith("ack: "))[5:])
        ps = text.split("ps (host process tree at capture):", 1)[1]
        rows = [l.split(None, 3) for l in ps.splitlines() if l[:1].isdigit()]
        assert any(int(r[0]) == ack["pid"] and "ui-tui/dist/entry.js" in r[3] for r in rows), e["capture_log"]
        assert ack["direction"] == "_ref" and ack["seq"] is not None


def test_e2e_mantle_sits_directly_above_the_composer(ref_run):
    # The crop is the widget's own box; the row right under it must be the ❯ composer line (spike 02).
    _, d = ref_run
    m = json.loads((d / "manifest.json").read_text())
    e = next(e for e in m["entries"] if e["scale"] == "M" and e["state"] == "needs-you" and e["depth"] == "truecolor"
             and e["cols"] == 120)
    sys.path.insert(0, str(ROOT / "tools"))
    import capture_tui as ct
    x, y, w, h = e["crop"]
    assert h == 2 * ct.CELL_H and w == 118 * ct.CELL_W            # 2 rows × (cols − 2)
    assert x == ct.CELL_W                                           # one blank column on the left
    img = PIL.Image.open(d / e["file"]).convert("RGB")
    below = img.crop((0, y + h, ct.CELL_W * 3, y + h + ct.CELL_H))
    assert len(below.getcolors(1 << 16)) > 1                           # the ❯ glyph is drawn there


def test_e2e_256_rung_uses_only_xterm256_colours(ref_run):
    _, d = ref_run
    cube = [0, 95, 135, 175, 215, 255]
    pal = {(r, g, b) for r in cube for g in cube for b in cube} | {(8 + 10 * i,) * 3 for i in range(24)}
    m = json.loads((d / "manifest.json").read_text())
    for e in m["entries"]:
        if e["depth"] != "256":
            continue
        im = PIL.Image.open(d / e["file"]).convert("RGB")
        x, y, w, h = e["crop"]
        # sample cell centres of the top pixel row (▀ fg) — glyph anti-aliasing lives elsewhere
        cols = {im.getpixel((x + cx * 9 + 4, y + 2)) for cx in range(20, w // 9 - 12)}
        assert cols <= pal, (e["file"], cols - pal)
