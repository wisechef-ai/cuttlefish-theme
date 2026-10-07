"""Pure maths + manifest parsing for the cf2909 P1 gates (G2 is built on this; G5 shares the CVD sims).

numpy + Pillow only. Every threshold lives in ``FROZEN`` and mirrors tools/p1/CONTRACT.md section 5; it is
not tunable here, and changing it is a logged deviation owned by the P1 lead.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SCHEMA = "cf2909.p1.manifest/1"

FROZEN = {
    "contrast_min": 4.5,              # WCAG 2.x, authoredPairs + rendered text cells
    "identity_delta_e_min": 0.020,    # nearest-pair dE_OK, at 16 and at 20 sessions
    "identity_arc_deg": (110.0, 340.0),
    "identity_min_chroma": 0.03,      # below this a tile claims no hue (unknown/degraded)
}

CELL_W, CELL_H = 11, 23               # terminator cell box in screen px (manifest crops are N*11 x M*23)


class ManifestError(ValueError):
    pass


# ---- colour ---------------------------------------------------------------------------------
def parse_hex(s: str) -> tuple[int, int, int]:
    s = str(s).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {s!r}")
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as e:
        raise ValueError(f"not a hex colour: {s!r}") from e


def srgb_to_linear(u8) -> np.ndarray:
    c = np.asarray(u8, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb_u8(lin) -> np.ndarray:
    c = np.clip(np.asarray(lin, dtype=np.float64), 0.0, 1.0)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.rint(s * 255.0).astype(np.uint8)


def relative_luminance(rgb) -> float:
    r, g, b = srgb_to_linear(np.array(rgb if not isinstance(rgb, str) else parse_hex(rgb), dtype=np.float64))
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


def contrast_ratio(a, b) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


def rgb_to_oklab(rgb_u8) -> np.ndarray:
    """(..., 3) uint8 sRGB -> (..., 3) OKLab (Ottosson 2020)."""
    lin = srgb_to_linear(rgb_u8)
    lms = np.cbrt(lin @ _M1.T)
    return lms @ _M2.T


def oklab_to_lch(lab) -> np.ndarray:
    lab = np.asarray(lab, dtype=np.float64)
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    return np.stack([lab[..., 0], c, h], axis=-1)


def delta_e_ok(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)))


def nearest_pair(labs):
    """Return (worst = smallest pairwise dE_OK, (i, j), full matrix). n < 2 -> (None, None, matrix)."""
    labs = np.asarray(labs, dtype=np.float64)
    d = np.linalg.norm(labs[:, None, :] - labs[None, :, :], axis=-1)
    n = len(labs)
    if n < 2:
        return None, None, d
    iu = np.triu_indices(n, k=1)
    k = int(np.argmin(d[iu]))
    return float(d[iu][k]), (int(iu[0][k]), int(iu[1][k])), d


def median_oklab(tile_rgb: np.ndarray, exclude: np.ndarray | None = None) -> np.ndarray:
    """Per-channel median OKLab of a tile, ignoring pixels where ``exclude`` is True (text pixels)."""
    px = tile_rgb.reshape(-1, 3)
    if exclude is not None:
        keep = ~exclude.reshape(-1)
        if keep.any():
            px = px[keep]
    return np.median(rgb_to_oklab(px), axis=0)


def non_background_mask(tile_rgb: np.ndarray, exclude: np.ndarray | None = None) -> np.ndarray:
    """True for pixels that are NOT the tile's dominant colour (or text): the 'pigment' of a sparse pattern."""
    px = tile_rgb.reshape(-1, 3)
    uniq, counts = np.unique(px, axis=0, return_counts=True)
    bg = uniq[int(np.argmax(counts))]
    m = np.any(tile_rgb != bg, axis=-1)
    return m & ~exclude if exclude is not None else m


def identity_check(labs, threshold: float = FROZEN["identity_delta_e_min"]) -> dict:
    labs = np.asarray(labs, dtype=np.float64)
    worst, pair, mat = nearest_pair(labs)
    lch = oklab_to_lch(labs)
    lo, hi = FROZEN["identity_arc_deg"]
    bad = [int(i) for i, (_, c, h) in enumerate(lch)
           if c >= FROZEN["identity_min_chroma"] and not (lo <= h < hi)]
    return {"threshold": threshold, "worst_pair": worst, "worst_indices": list(pair) if pair else None,
            "ok_delta": worst is None or worst >= threshold, "alarm_arc_violations": bad,
            "lch": lch.tolist(), "matrix": mat.tolist()}


# ---- Machado 2009, severity 1.0 (published table, applied in linear RGB) -------------------------
_MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}
CVD_KINDS = tuple(_MACHADO)


def machado_matrix(kind: str) -> np.ndarray:
    if kind not in _MACHADO:
        raise ValueError(f"unknown CVD kind {kind!r}; expected one of {CVD_KINDS}")
    return np.array(_MACHADO[kind], dtype=np.float64)


def simulate_cvd(img_rgb: np.ndarray, kind: str) -> np.ndarray:
    m = machado_matrix(kind)
    lin = srgb_to_linear(img_rgb[..., :3])
    return linear_to_srgb_u8(lin @ m.T)


# ---- pixels ---------------------------------------------------------------------------------
def frames_identical(frames: list[np.ndarray]) -> bool:
    return all(f.shape == frames[0].shape and np.array_equal(f, frames[0]) for f in frames[1:])


def measure_cell_contrast(cell_rgb: np.ndarray) -> float:
    """Glyph-vs-cell contrast of one rendered text cell.

    bg = the cell's most common colour; fg = mean of the ~4% of pixels farthest from bg in OKLab (glyph cores,
    not anti-aliased edges). Returns the WCAG ratio of those two colours.
    """
    px = cell_rgb.reshape(-1, 3)
    uniq, counts = np.unique(px, axis=0, return_counts=True)
    bg = uniq[int(np.argmax(counts))]
    if len(uniq) == 1:
        return 1.0
    lab = rgb_to_oklab(px)
    dist = np.linalg.norm(lab - rgb_to_oklab(bg[None, :])[0], axis=1)
    k = max(1, int(round(len(px) * 0.04)))
    idx = np.argsort(dist)[-k:]
    fg = px[idx].mean(axis=0)
    return contrast_ratio(tuple(fg), tuple(float(x) for x in bg))


# ---- manifest -------------------------------------------------------------------------------
_REQ = {"file": str, "host": str, "scale": str, "state": str, "rung": str, "depth": str,
        "sessions": list, "crop": list, "frame_t": (int, float)}


@dataclass
class Entry:
    file: str
    host: str
    scale: str
    state: str
    rung: str
    depth: str
    cols: int | None
    session_idx: int | None
    sessions: list
    frame_t: float
    crop: list
    degraded: bool = False
    tiles: list = field(default_factory=list)
    capture_log: str | None = None

    @property
    def look(self) -> str:
        return "degraded" if self.degraded else self.state

    @property
    def grid_n(self) -> int | None:
        return len(self.sessions) if len(self.sessions) in (16, 20) and self.tiles else None


@dataclass
class Manifest:
    path: Path
    direction: str
    entries: list[Entry]
    raw: dict

    @property
    def root(self) -> Path:
        return self.path.parent

    def frame_groups(self) -> "OrderedDict[tuple, list[Entry]]":
        g: OrderedDict = OrderedDict()
        for e in self.entries:
            key = (e.host, e.scale, e.rung, e.depth, e.cols, tuple(e.sessions), e.look)
            g.setdefault(key, []).append(e)
        for v in g.values():
            v.sort(key=lambda e: e.frame_t)
        return g


def load_manifest(path) -> Manifest:
    p = Path(path)
    try:
        raw = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ManifestError(f"cannot read manifest {p}: {e}") from e
    if raw.get("schema") != SCHEMA:
        raise ManifestError(f"schema must be {SCHEMA!r}, got {raw.get('schema')!r}")
    if not isinstance(raw.get("direction"), str) or not raw["direction"]:
        raise ManifestError("manifest has no direction id")
    entries = []
    for n, e in enumerate(raw.get("entries") or []):
        for k, t in _REQ.items():
            if not isinstance(e.get(k), t):
                raise ManifestError(f"entry {n} ({e.get('file')}): field {k!r} missing or not {t}")
        entries.append(Entry(file=e["file"], host=e["host"], scale=e["scale"], state=e["state"], rung=e["rung"],
                             depth=e["depth"], cols=e.get("cols"), session_idx=e.get("session_idx"),
                             sessions=list(e["sessions"]), frame_t=float(e["frame_t"]), crop=list(e["crop"]),
                             degraded=bool(e.get("degraded")), tiles=list(e.get("tiles") or []),
                             capture_log=e.get("capture_log")))
    return Manifest(path=p, direction=raw["direction"], entries=entries, raw=raw)
