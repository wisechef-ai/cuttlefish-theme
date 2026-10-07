"""Bridge to the direction module (via node) and shared pixel helpers for G2/G5."""
from __future__ import annotations

import base64
import functools
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import gatelib as gl

GATES = Path(__file__).resolve().parent
REPO = GATES.parent
FIXTURE = REPO / "tools" / "p1" / "stub-sessions.json"
NODE_HELPER = GATES / "node" / "paint_dump.mjs"


class DirectionError(RuntimeError):
    pass


def resolve_direction_dir(direction_id: str, hint: str | None = None) -> Path:
    cands = [Path(hint)] if hint else [REPO / "design" / "directions" / direction_id,
                                       GATES / "tests" / "fixtures" / direction_id]
    for c in cands:
        if (c / "direction.mjs").is_file():
            return c.resolve()
    raise DirectionError(f"no direction.mjs for {direction_id!r} (looked in {[str(c) for c in cands]}); pass --direction-dir")


def run_node(direction_dir: Path, requests: list[dict], authored: bool = False, timeout: int = 120) -> dict:
    payload = {"direction_dir": str(direction_dir), "fixture": str(FIXTURE), "authored": authored, "requests": requests}
    p = subprocess.run(["node", str(NODE_HELPER)], input=json.dumps(payload), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise DirectionError(f"node helper failed for {direction_dir}: {p.stderr.strip()[:500]}")
    return json.loads(p.stdout)


def decode_pixels(b64: str, w: int, h: int) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype=np.uint8).reshape(h, w, 4)


# ---- entry pixels ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=48)
def load_png(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def load_entry_crop(man: gl.Manifest, e: gl.Entry) -> np.ndarray:
    img = load_png(man.root / e.file)
    x, y, w, h = e.crop
    return img[y:y + h, x:x + w]


def tui_cell_size(e: gl.Entry) -> tuple[int, int, int, int]:
    """(w_px, h_px, cols, rows) of a terminator half-rung entry's crop in cells."""
    cols = max(1, round(e.crop[2] / gl.CELL_W)); rows = max(1, round(e.crop[3] / gl.CELL_H))
    return cols, rows * 2, cols, rows


def text_requests(e: gl.Entry, crop: list | None = None) -> dict:
    """The paint() request that reproduces what the TUI host drew for this entry (text overlay positions)."""
    crop = crop or e.crop
    cols = max(1, round(crop[2] / gl.CELL_W)); rows = max(1, round(crop[3] / gl.CELL_H))
    return {"scale": e.scale, "w": cols, "h": rows * 2, "state": e.state, "session_idx": e.session_idx if not e.degraded else None,
            "degraded": e.degraded, "t": e.frame_t, "depth": e.depth}


def text_cell_boxes(texts: list[dict]) -> list[tuple[int, int, int, int, str]]:
    """paint().text (cell coords) -> pixel boxes (x, y, w, h, str) in the crop's coordinate space."""
    out = []
    for t in texts:
        s = str(t.get("str", ""))
        if not s:
            continue
        out.append((round(t["x"]) * gl.CELL_W, round(t["y"]) * gl.CELL_H, len(s) * gl.CELL_W, gl.CELL_H, s))
    return out


# ---- CVD images next to the manifest -----------------------------------------------------------
def cvd_path(man: gl.Manifest, kind: str, e: gl.Entry) -> Path:
    return man.root / "cvd" / kind / Path(e.file).with_suffix(".png")


def ensure_cvd_images(man: gl.Manifest, scales=("M", "S")) -> list[Path]:
    """Machado-2009 sims (severity 1.0) of every M/S render's crop, written under <manifest dir>/cvd/<kind>/."""
    written = []
    for e in man.entries:
        if e.scale not in scales:
            continue
        crop = load_entry_crop(man, e)
        for kind in gl.CVD_KINDS:
            out = cvd_path(man, kind, e)
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(gl.simulate_cvd(crop, kind)).save(out)
            written.append(out)
    return written
