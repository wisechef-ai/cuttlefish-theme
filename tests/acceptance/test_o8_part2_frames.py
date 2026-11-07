"""ACCEPTANCE CONTRACT PART 2 — O8: the demo's FRAMES are the capture's frames (closes luna-parts L8) (locked with the parts).

Part 1 checks cut.json's arithmetic, not the pixels: a video of one repeated still, or one whose segments are cut from
    the wrong minute of the
capture, satisfies it. Here, with ffmpeg/ffprobe:
  * for every `capture` segment: the demo frame at its OUTPUT midpoint, (start+end)/2, must match the O7 capture frame
      at the declared SOURCE time,
    in + (start+end)/2 − start, with PSNR >= 30 dB (both scaled to 640 px wide);
  * the opener: seg[0] (the legend card) declares `card_png` (a path relative to kit/video/) and `card_png_sha256`; the
      demo frames at t = 1, 5 and 9 s
    must each match that PNG with PSNR >= 30 dB (so the card must still be on screen at 9 s).
Negative controls (run on tiny synthetic videos built in a tmp dir by these tests, nothing committed): a still
    repeated for every segment fails;
a segment cut from the wrong time but labelled with the declared one fails; a different card fails.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import ROOT
from .test_o8_submission_kit import KIT

MANIFEST = ROOT / "evidence" / "v2" / "manifest.json"
MIN_PSNR_DB = 30.0
OPENER_TIMES = (1.0, 5.0, 9.0)
WIDTH = 640


def need_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.fail("ffmpeg and ffprobe are needed to check the demo's frames")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def extract_frame(video: Path, t: float, out: Path) -> Path:
    r = run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
            "-vf", f"scale={WIDTH}:-2", str(out))
    if r.returncode != 0 or not out.is_file():
        raise ValueError(f"cannot extract a frame at {t:.3f}s of {video}: {r.stderr.strip()[-200:]}")
    return out


def scaled_png(png: Path, out: Path) -> Path:
    r = run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(png), "-vf", f"scale={WIDTH}:-2", str(out))
    if r.returncode != 0:
        raise ValueError(f"cannot read {png}: {r.stderr.strip()[-200:]}")
    return out


def psnr(a: Path, b: Path) -> float:
    r = run("ffmpeg", "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "psnr", "-f", "null", "-")
    m = re.search(r"average:(\S+)", r.stderr)
    if not m:
        raise ValueError(f"no PSNR for {a.name} vs {b.name} (different sizes?): {r.stderr.strip()[-200:]}")
    return math.inf if m.group(1) == "inf" else float(m.group(1))


def match_problem(label: str, a: Path, b: Path) -> str | None:
    try:
        db = psnr(a, b)
    except ValueError as e:
        return f"{label}: {e}"
    return None if db >= MIN_PSNR_DB else f"{label}: PSNR {db:.1f} dB < {MIN_PSNR_DB:.0f} dB"


def segment_problems(i: int, seg: dict, demo: Path, capture: Path, tmp: Path) -> list[str]:
    mid = (seg["start"] + seg["end"]) / 2
    src_t = seg["in"] + (mid - seg["start"])
    a = extract_frame(demo, mid, tmp / f"d{i}.png")
    b = extract_frame(capture, src_t, tmp / f"s{i}.png")
    p = match_problem(f"segments[{i}] demo@{mid:.2f}s vs capture@{src_t:.2f}s ({seg.get('state')})", a, b)
    return [p] if p else []


def opener_problems(card: dict, kit_video: Path, demo: Path, tmp: Path) -> list[str]:
    png = kit_video / str(card.get("card_png", ""))
    if not card.get("card_png") or not png.is_file():
        return [f"segments[0].card_png {card.get('card_png')!r} is not a file next to cut.json"]
    if hashlib.sha256(png.read_bytes()).hexdigest() != card.get("card_png_sha256"):
        return ["segments[0].card_png_sha256 is not the sha256 of card_png"]
    ref = scaled_png(png, tmp / "card.png")
    bad = []
    for t in OPENER_TIMES:
        p = match_problem(f"opener t={t:g}s vs the legend card", extract_frame(demo, t, tmp / f"o{t:g}.png"), ref)
        if p:
            bad.append(p)
    return bad


def frame_problems(cut: dict, kit_video: Path, demo: Path, capture: Path, tmp: Path) -> list[str]:
    need_ffmpeg()
    segs = cut["segments"]
    bad = opener_problems(segs[0], kit_video, demo, tmp)
    for i, seg in enumerate(segs):
        if seg.get("kind") == "capture":
            bad += segment_problems(i, seg, demo, capture, tmp)
    return bad


# ---- the kit ------------------------------------------------------------------------------------------------------------

def test_F1_the_demo_frames_come_from_the_capture_and_the_opener_is_the_legend_card(tmp_path):
    cut_file = KIT / "video" / "cut.json"
    assert cut_file.is_file(), f"{cut_file} missing: the edit decision list of the demo"
    assert MANIFEST.is_file(), f"{MANIFEST.relative_to(ROOT)} missing: the capture the frames are compared with"
    cut = json.loads(cut_file.read_text())
    manifest = json.loads(MANIFEST.read_text())
    demo = KIT / "video" / cut.get("output", "cuttlefish-v2-demo.mp4")
    capture = ROOT / manifest["capture"]["video"]
    assert demo.is_file() and capture.is_file()
    digest = hashlib.sha256(capture.read_bytes()).hexdigest()
    assert digest == manifest["capture"]["video_sha256"], "the capture is not the one the manifest names"
    assert frame_problems(cut, KIT / "video", demo, capture, tmp_path) == []


# ---- negative controls on synthetic videos (ffmpeg lavfi; built per test in tmp_path) ---------------------------------------

ENC = ("-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-crf", "10", "-pix_fmt", "yuv420p", "-r", "10")


def ff(*args: str) -> None:
    r = run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args)
    assert r.returncode == 0, r.stderr


def build(tmp: Path, wrong_time: bool = False, repeat_still: bool = False, other_card: bool = False):
    """A 20 s synthetic capture, a legend card PNG, and a demo = card (0-9.5 s) + 4 capture segments of 2 s from in = 2, 6, 10, 14."""
    need_ffmpeg()
    capture, card = tmp / "capture.mp4", tmp / "legend.png"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=20", *ENC, str(capture))
    ff("-f", "lavfi", "-i", "smptebars=s=320x180", "-frames:v", "1", str(card))
    parts = []
    ff("-loop", "1", "-i", str(tmp / "legend.png" if not other_card else _other(tmp)), "-t", "9.5", *ENC, str(tmp / "p0.mp4"))
    parts.append(tmp / "p0.mp4")
    segs = [{"kind": "card", "name": "legend", "start": 0.0, "end": 9.5, "card_png": "legend.png",
             "card_png_sha256": hashlib.sha256(card.read_bytes()).hexdigest()}]
    t = 9.5
    for k, src_in in enumerate((2.0, 6.0, 10.0, 14.0)):
        part = tmp / f"p{k + 1}.mp4"
        real_in = src_in + 3.0 if wrong_time else src_in
        if repeat_still:
            ff("-ss", "3", "-i", str(capture), "-frames:v", "1", str(tmp / "still.png"))
            ff("-loop", "1", "-i", str(tmp / "still.png"), "-t", "2", *ENC, str(part))
        else:
            ff("-ss", str(real_in), "-i", str(capture), "-t", "2", *ENC, str(part))
        parts.append(part)
        segs.append({"kind": "capture", "start": t, "end": t + 2, "in": src_in, "out": src_in + 2, "state": "working"})
        t += 2
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    demo = tmp / "demo.mp4"
    ff("-f", "concat", "-safe", "0", "-i", str(lst), *ENC, str(demo))
    return {"segments": segs}, demo, capture


def _other(tmp: Path) -> Path:
    other = tmp / "other.png"
    ff("-f", "lavfi", "-i", "testsrc=s=320x180", "-frames:v", "1", str(other))
    return other


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    """variant name → (cut, demo, capture, dir), each built once."""
    made = {}

    def get(name: str):
        if name not in made:
            d = tmp_path_factory.mktemp(name)
            kwargs = {"good": {}, "wrong_time": {"wrong_time": True}, "repeat": {"repeat_still": True},
                      "other_card": {"other_card": True}}[name]
            (d / "w").mkdir()
            made[name] = (*build(d, **kwargs), d)
        return made[name]
    return get


def test_F2_a_faithful_synthetic_demo_passes(synth):
    cut, demo, capture, d = synth("good")
    assert frame_problems(cut, d, demo, capture, d / "w") == []


def test_F3_a_still_repeated_for_every_segment_fails(synth):
    cut, demo, capture, d = synth("repeat")
    bad = frame_problems(cut, d, demo, capture, d / "w")
    assert len([b for b in bad if b.startswith("segments[")]) >= 3, bad


def test_F4_a_segment_cut_from_the_wrong_time_but_labelled_with_the_declared_one_fails(synth):
    cut, demo, capture, d = synth("wrong_time")
    bad = frame_problems(cut, d, demo, capture, d / "w")
    assert len([b for b in bad if b.startswith("segments[")]) == 4, bad


def test_F5_a_different_opener_card_fails_at_all_three_times(synth):
    cut, demo, capture, d = synth("other_card")
    bad = frame_problems(cut, d, demo, capture, d / "w")
    assert len([b for b in bad if b.startswith("opener")]) == 3, bad


def test_F6_card_declaration_problems_and_psnr_arithmetic(synth):
    cut, demo, capture, d = synth("good")
    w = d / "w"
    card = dict(cut["segments"][0])
    assert opener_problems({**card, "card_png": ""}, d, demo, w)
    assert opener_problems({**card, "card_png": "missing.png"}, d, demo, w)
    wrong_hash = opener_problems({**card, "card_png_sha256": "0" * 64}, d, demo, w)
    assert wrong_hash == ["segments[0].card_png_sha256 is not the sha256 of card_png"]
    a = extract_frame(demo, 1.0, w / "a.png")
    assert psnr(a, a) == math.inf
    b = extract_frame(capture, 5.0, w / "b.png")
    assert psnr(a, b) < MIN_PSNR_DB
    with pytest.raises(ValueError):
        extract_frame(demo, 1.0, w / "nodir" / "x.png")
    other_size = d / "wide.png"
    ff("-f", "lavfi", "-i", "testsrc=s=320x90", "-frames:v", "1", str(other_size))
    with pytest.raises(ValueError):
        psnr(a, scaled_png(other_size, w / "wide640.png"))
