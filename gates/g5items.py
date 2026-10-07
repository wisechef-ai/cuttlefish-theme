"""G5 work items: what each blind vision call is shown. Images are built from the manifest's render crops only.

kinds: aesthetic (one image), legend (legend sheet over one unlabelled sample, optionally CVD-simulated), identity
(16-tile lettered sheet over one unlabelled tile crop, text masked on both).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import dirtools as dt
import g5lib
import gatelib as gl

PROMPTS = Path(__file__).resolve().parent / "g5_prompts"
PHOTOS = Path(__file__).resolve().parent / "photos"
FONT = ImageFont.load_default(size=18)
LEGEND_ORDER = ("idle", "working", "review", "needs-you", "fault", "unknown")
MIN_W, MAX_W = 480, 1400


@dataclass
class Item:
    id: str
    kind: str          # aesthetic | legend | identity
    family: str        # XL | M | S | photo | identity
    variant: str       # plain | deutan | protan | tritan
    truth: object
    image: Image.Image
    prompt_file: str
    task: str          # parse task: score | label | match
    source: str = ""

    @property
    def prompt(self) -> str:
        return (PROMPTS / self.prompt_file).read_text().strip()


def prep(img: Image.Image) -> Image.Image:
    """Integer nearest-neighbour upscale of tiny crops (no blur), LANCZOS downscale of huge ones."""
    img = img.convert("RGB")
    if img.width < MIN_W:
        k = -(-MIN_W // img.width)
        img = img.resize((img.width * k, img.height * k), Image.NEAREST)
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
    return img


def stack(top: Image.Image, bottom: Image.Image, gap: int = 14) -> Image.Image:
    w = max(top.width, bottom.width)
    out = Image.new("RGB", (w, top.height + gap + bottom.height), (255, 255, 255))
    out.paste(top, (0, 0)); out.paste(bottom, (0, top.height + gap))
    return out


def legend_sheet(rows: list[tuple[str, Image.Image]]) -> Image.Image:
    rows = [(lab, prep(im)) for lab, im in rows]
    lab_w = 140
    w = lab_w + max(im.width for _, im in rows)
    h = sum(im.height + 8 for _, im in rows)
    sheet = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    y = 0
    for lab, im in rows:
        d.text((6, y + im.height / 2), lab, font=FONT, fill=(0, 0, 0), anchor="lm")
        sheet.paste(im, (lab_w, y))
        y += im.height + 8
    return sheet


_FIXTURE = json.loads(dt.FIXTURE.read_text())
_NAMES = {s["name"] for s in _FIXTURE["sessions"]} | {_FIXTURE["degraded"]["name"]}


def _blank_text(man: gl.Manifest, direction_dir: Path, e: gl.Entry, arr: np.ndarray, keep_alarm: bool) -> np.ndarray:
    """Paint over the text cells of a TUI render so the legend tests the pattern, not the words: the session name always
    (the same name sits in the legend row and in its sample), and by default the alarm words / '?' too (text legibility is
    G2's job). Only hosts whose cell geometry is known (terminator half rung) can be masked; others keep their text."""
    if e.host != "tui-terminator" or e.rung != "half" or e.tiles:
        return arr
    arr = arr.copy()
    fill = _mode_colour(arr)
    for bx, by, bw, bh, s in dt.text_cell_boxes(dt.run_node(direction_dir, [dt.text_requests(e)])["results"][0]["text"]):
        if not keep_alarm or s.strip() in _NAMES:
            arr[by:by + bh, bx:bx + bw] = fill
    return arr


def _crop_img(man: gl.Manifest, e: gl.Entry, cvd: str | None, direction_dir: Path | None = None, keep_alarm: bool = False) -> Image.Image:
    arr = dt.load_entry_crop(man, e)
    if direction_dir is not None:
        arr = _blank_text(man, direction_dir, e, arr, keep_alarm)
    return Image.fromarray(gl.simulate_cvd(arr, cvd) if cvd else arr)


def _singles(man, scale, host=None):
    return [e for e in man.entries if e.scale == scale and not e.tiles and len(e.sessions) <= 1 and (host is None or e.host == host)]


def _first_per_group(entries: list[gl.Entry]) -> list[gl.Entry]:
    seen, out = set(), []
    for e in sorted(entries, key=lambda e: e.frame_t):
        k = (e.host, e.scale, e.rung, e.depth, e.cols, tuple(e.sessions), e.look)
        if k not in seen:
            seen.add(k); out.append(e)
    return out


def legend_source(man: gl.Manifest, family: str) -> dict[str, gl.Entry]:
    """The direction's own labelled legend: the first frame of each of the six states on the primary rung of this scale."""
    if family == "XL":
        pool = [e for e in _singles(man, "XL", "desktop")]
    else:
        pool = [e for e in _singles(man, family, "tui-terminator") if e.rung == "half" and e.depth == "truecolor" and e.cols in (120, None)]
    return {e.look: e for e in _first_per_group(pool) if e.look in LEGEND_ORDER}


def legend_items(man: gl.Manifest, direction_dir: Path, family: str, cvd: str | None, keep_alarm: bool = False) -> list[Item]:
    src = legend_source(man, family)
    if set(src) != set(LEGEND_ORDER):
        return []
    sheet = legend_sheet([(g5lib.STATE_TO_LABEL[s], _crop_img(man, src[s], cvd, direction_dir, keep_alarm)) for s in LEGEND_ORDER])
    legend_files = {e.file for e in src.values()}
    pool = [e for e in _singles(man, family) if e.file not in legend_files]
    firsts = {e.file for e in _first_per_group(pool)}
    pool = [e for e in pool if e.file in firsts or (e.look == "working" and not cvd)]   # static looks repeat byte-for-byte: ask once
    out = []
    for e in pool:
        out.append(Item(id=f"legend-{family}-{cvd or 'plain'}-{Path(e.file).stem}", kind="legend", family=family, variant=cvd or "plain",
                        truth=g5lib.STATE_TO_LABEL[e.look], image=stack(sheet, prep(_crop_img(man, e, cvd, direction_dir, keep_alarm))),
                        prompt_file="legend.txt", task="label", source=e.file))
    return out


def aesthetic_items(man: gl.Manifest) -> list[Item]:
    picks = []
    picks += [(e, "XL") for e in _first_per_group(_singles(man, "XL", "desktop"))]
    picks += [(e, "M") for e in _first_per_group(_singles(man, "M")) if e.depth == "truecolor" and e.rung in ("half", "dom")]
    picks += [(e, "S") for e in _first_per_group(_singles(man, "S")) if e.depth == "truecolor"]
    items = [Item(id=f"aesthetic-{fam}-{Path(e.file).stem}", kind="aesthetic", family=fam, variant="plain", truth=None,
                  image=prep(_crop_img(man, e, None)), prompt_file="aesthetic_xl.txt" if fam == "XL" else "aesthetic_ms.txt",
                  task="score", source=e.file) for e, fam in picks]
    for p in sorted(PHOTOS.glob("p*.jpg")):
        items.append(Item(id=f"aesthetic-photo-{p.stem}", kind="aesthetic", family="photo", variant="plain", truth=None,
                          image=prep(Image.open(p)), prompt_file="aesthetic_xl.txt", task="score", source=f"photos/{p.name}"))
    return items


# ---- identity -------------------------------------------------------------------------------
def _masked_tiles(man: gl.Manifest, direction_dir: Path, e: gl.Entry) -> list[Image.Image]:
    """Each tile of an identity grid as an image, with the text cells painted over with the tile's own background."""
    img = dt.load_png(man.root / e.file)
    tiles = sorted(e.tiles, key=lambda t: t["session_idx"])
    reqs = [{"scale": "S", "w": round(t["crop"][2] / gl.CELL_W), "h": round(t["crop"][3] / gl.CELL_H) * 2, "state": e.state,
             "session_idx": t["session_idx"], "degraded": False, "t": e.frame_t, "depth": e.depth} for t in tiles]
    texts = dt.run_node(direction_dir, reqs)["results"]
    out = []
    for t, r in zip(tiles, texts):
        x, y, w, h = t["crop"]
        tile = img[y:y + h, x:x + w].copy()
        fill = _mode_colour(tile)
        for bx, by, bw, bh, _s in dt.text_cell_boxes(r["text"]):
            tile[by:by + bh, bx:bx + bw] = fill
        out.append(Image.fromarray(tile))
    return out


def _mode_colour(tile: np.ndarray) -> np.ndarray:
    uniq, counts = np.unique(tile.reshape(-1, 3), axis=0, return_counts=True)
    return uniq[int(np.argmax(counts))]


def identity_sheet(tiles: list[Image.Image]) -> Image.Image:
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles)
    cap, gap = 24, 10
    sheet = Image.new("RGB", (4 * tw + 3 * gap, 4 * (th + cap) + 3 * gap), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(tiles[:16]):
        x, y = (i % 4) * (tw + gap), (i // 4) * (th + cap + gap)
        d.text((x + 4, y + 2), g5lib.LETTERS[i], font=FONT, fill=(0, 0, 0))
        sheet.paste(t, (x, y + cap))
    return sheet


def identity_items(man: gl.Manifest, direction_dir: Path, seed: int) -> list[Item]:
    g16 = [e for e in man.entries if e.grid_n == 16 and e.host == "tui-terminator"]
    g20 = [e for e in man.entries if e.grid_n == 20 and e.host == "tui-terminator"]
    if not g16 or not g20:
        return []
    sheet = identity_sheet(_masked_tiles(man, direction_dir, min(g16, key=lambda e: e.frame_t)))
    crops = _masked_tiles(man, direction_dir, min(g20, key=lambda e: e.frame_t))[:16]
    order = g5lib.seeded_shuffle(list(range(16)), seed)
    return [Item(id=f"identity-{n:02d}-s{i:02d}", kind="identity", family="identity", variant="plain", truth=g5lib.LETTERS[i],
                 image=stack(sheet, crops[i]), prompt_file="identity.txt", task="match", source=f"grid20 tile {i}")
            for n, i in enumerate(order)]


TASKS = ("aesthetic", "legend", "identity")


def build_items(man: gl.Manifest, direction_dir: Path, seed: int, tasks=TASKS, keep_alarm_text: bool = False) -> list[Item]:
    items = aesthetic_items(man) if "aesthetic" in tasks else []
    if "legend" in tasks:
        for fam in ("XL", "M", "S"):
            items += legend_items(man, direction_dir, fam, None, keep_alarm_text)
        for kind in gl.CVD_KINDS:
            for fam in ("M", "S"):
                items += legend_items(man, direction_dir, fam, kind, keep_alarm_text)
    if "identity" in tasks:
        items += identity_items(man, direction_dir, seed)
    return items
