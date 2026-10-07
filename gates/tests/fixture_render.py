"""Synthetic render matrix for the gate instruments (NOT real-host evidence).

Paints a throwaway direction through ``tools/p1/stub-sessions.json`` into PNGs that follow the same geometry as the
real TUI host (11x23 px cells, half-block rung, 4-wide identity grid) plus desktop-style flat renders, and writes a
CONTRACT section-4 manifest. Used to prove G2/G5 on a known-good and a known-bad direction.

    gates/.venv/bin/python gates/tests/fixture_render.py gates/tests/fixtures/good <out-dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dirtools as dt  # noqa: E402
import gatelib as gl  # noqa: E402

CW, CH = gl.CELL_W, gl.CELL_H
LOOKS = ("idle", "working", "review", "needs-you", "fault", "unknown", "degraded")
CUBE = np.array([0, 95, 135, 175, 215, 255])
GREYS = np.arange(8, 239, 10)
FONT = ImageFont.load_default(size=15)
LOG = "logs/synthetic-fixture.log"


def quant256(rgb) -> np.ndarray:
    """Nearest xterm-256 colour (6x6x6 cube + 24 greys) for an (..., 3) array."""
    a = np.asarray(rgb, dtype=np.int32)
    cube = CUBE[np.abs(a[..., None] - CUBE).argmin(-1)]
    g = GREYS[np.abs(a.mean(-1)[..., None] - GREYS).argmin(-1)]
    grey = np.repeat(g[..., None], 3, axis=-1)
    use_grey = (((a - grey) ** 2).sum(-1) < ((a - cube) ** 2).sum(-1))[..., None]
    return np.where(use_grey, grey, cube).astype(np.uint8)


def paint_cells(px: np.ndarray, text: list, w: int, rows: int, depth: str) -> Image.Image:
    """Half-block cells (top half = px[2y], bottom half = px[2y+1]); text cells get their bg plus a glyph."""
    q = quant256 if depth == "256" else (lambda c: np.asarray(c, dtype=np.uint8))
    rgb = q(px[..., :3])
    arr = np.zeros((rows * CH, w * CW, 3), dtype=np.uint8)
    for y in range(rows):
        for x in range(w):
            arr[y * CH:y * CH + 11, x * CW:(x + 1) * CW] = rgb[2 * y, x]
            arr[y * CH + 11:(y + 1) * CH, x * CW:(x + 1) * CW] = rgb[2 * y + 1, x]
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    for t in text:
        bg = tuple(int(v) for v in q(np.array(gl.parse_hex(t["bg"]))))
        fg = tuple(int(v) for v in q(np.array(gl.parse_hex(t["fg"]))))
        for k, ch in enumerate(t["str"]):
            x, y = round(t["x"]) + k, round(t["y"])
            if 0 <= x < w and 0 <= y < rows:
                d.rectangle([x * CW, y * CH, (x + 1) * CW - 1, (y + 1) * CH - 1], fill=bg)
                d.text((x * CW + CW / 2, y * CH + CH / 2), ch, font=FONT, fill=fg, anchor="mm")
    return img


def paint_flat(px: np.ndarray, text: list) -> Image.Image:
    img = Image.fromarray(px[..., :3].copy())
    d = ImageDraw.Draw(img)
    for t in text:
        d.text((t["x"], t["y"]), t["str"], font=FONT, fill=gl.parse_hex(t["fg"]))
    return img


def pad(img: Image.Image, xy) -> Image.Image:
    c = Image.new("RGB", (img.width + 2 * xy[0], img.height + 2 * xy[1]), (0, 0, 0))
    c.paste(img, xy)
    return c


class Painter:
    def __init__(self, direction_dir: Path):
        self.dir = direction_dir

    def pixels(self, scale, w, h, state, degraded, sess, t, depth="truecolor"):
        r = dt.run_node(self.dir, [{"scale": scale, "w": w, "h": h, "state": state, "session_idx": sess, "degraded": degraded,
                                    "t": t, "depth": depth, "pixels": True}])["results"][0]
        return dt.decode_pixels(r["pixels_b64"], w, h), r["text"]


def build(direction_dir: Path, out: Path) -> Path:
    out = Path(out)
    (out / "tui").mkdir(parents=True, exist_ok=True); (out / "desktop").mkdir(exist_ok=True)
    fx = json.loads(dt.FIXTURE.read_text())
    pen = Painter(direction_dir)
    meta = dt.run_node(direction_dir, [])["meta"]
    entries = []

    def add(look, t, *, host, scale, rung, depth, cols, name, w, h):
        state = "unknown" if look == "degraded" else look
        sess = None if look == "degraded" else next(s["idx"] for s in fx["sessions"] if s["state"] == look)
        px, text = pen.pixels(scale, w, h, state, look == "degraded", sess, t, depth)
        tui = host == "tui-terminator"
        img = paint_cells(px, text, w, h // 2, depth) if tui else paint_flat(px, text)
        stem = f"{name}-t{int(t * 100):03d}.png"
        rel = ("tui/" if tui else "desktop/") + stem
        origin = (12, 40) if tui else (0, 0)
        (pad(img, origin) if tui else img).save(out / rel)
        entries.append({"file": rel, "host": host, "scale": scale, "state": state, "rung": rung, "depth": depth, "cols": cols,
                        "session_idx": sess, "sessions": [sess if sess is not None else 0], "frame_t": t,
                        "crop": [*origin, *img.size], "capture_log": LOG, "degraded": look == "degraded"})

    for look in LOOKS:
        for t in ((0.0, 0.25, 0.5, 0.75) if look == "working" else (0.0, 0.5)):
            for depth, tag in (("truecolor", "tc"), ("256", "256")):
                add(look, t, host="tui-terminator", scale="M", rung="half", depth=depth, cols=120, name=f"M-half-{tag}-120-{look}", w=118, h=4)
            for scale, w, h in (("XL", 320, 120), ("M", 120, 24), ("S", 24, 16)):
                add(look, t, host="desktop", scale=scale, rung="dom", depth="truecolor", cols=None, name=f"{scale}-{look}", w=w, h=h)
            if look != "degraded":
                add(look, t, host="tui-terminator", scale="S", rung="half", depth="truecolor", cols=120, name=f"S-pill-half-tc-120-{look}", w=14, h=2)
    entries += [grid(pen, out, n, t) for n in (16, 20) for t in (0.0, 0.5)]
    path = out / "manifest.json"
    path.write_text(json.dumps({"schema": gl.SCHEMA, "direction": meta["id"], "synthetic": True,
                                "note": "synthetic fixture render, not real-host evidence", "direction_meta": meta, "entries": entries}, indent=1))
    return path


def grid(pen: Painter, out: Path, n: int, t: float) -> dict:
    tw, rows_per_tile, step_x, step_y, x0, y0 = 28, 2, 29 * CW, 3 * CH, 45, 40
    n_rows = (n + 3) // 4
    W, H = 4 * step_x - CW, n_rows * step_y - CH
    img = Image.new("RGB", (W, H), (0, 0, 0))
    tiles = []
    for i in range(n):
        px, text = pen.pixels("S", tw, rows_per_tile * 2, "idle", False, i, t)
        tile = paint_cells(px, text, tw, rows_per_tile, "truecolor")
        gx, gy = (i % 4) * step_x, (i // 4) * step_y
        img.paste(tile, (gx, gy))
        tiles.append({"session_idx": i, "crop": [x0 + gx, y0 + gy, tile.width, tile.height]})
    rel = f"tui/S-grid{n}-half-tc-120-idle-t{int(t * 100):03d}.png"
    pad(img, (x0, y0)).save(out / rel)
    return {"file": rel, "host": "tui-terminator", "scale": "S", "state": "idle", "rung": "half", "depth": "truecolor", "cols": 120,
            "session_idx": None, "sessions": list(range(n)), "frame_t": t, "crop": [x0, y0, W, H], "capture_log": LOG,
            "degraded": False, "tiles": tiles}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(build(Path(sys.argv[1]), Path(sys.argv[2])))
