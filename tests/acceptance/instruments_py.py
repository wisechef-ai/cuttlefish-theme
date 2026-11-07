"""ACCEPTANCE CONTRACT PART — the measuring instruments of desktop/test/acceptance/instruments.ts, ported to Python (locked).

Used by test_o7_part1_recompute.py to RECOMPUTE the real-Desktop pixel numbers from raw PNG stills with exactly the
maths O2 applies to a rendered model. Pinned against the same published/constructed reference values as
instruments.test.ts (see test_instruments_py.py), and cross-checked against the TS instruments through node.

Also here: a stdlib-only PNG reader (8-bit, non-interlaced, colour type 0/2/4/6) and the pixel → dots detector that the
raw-evidence schema (contract/RAW-EVIDENCE.md) pins:
  1. crop to `region`, ignore `exclude` rectangles;
  2. ground = the most frequent colour of the cropped pixels;
  3. a pixel is ink when |ΔL| (OKLab L vs the ground) >= INK_THRESHOLD;
  4. organs = 4-connected ink components with MIN_AREA <= area <= MAX_AREA pixels;
  5. dot = centroid, r = sqrt(area/π), colour = the component's mean colour, alpha 1 (so dotΔL = the component's ΔL).
"""
from __future__ import annotations

import math
import struct
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

INK_THRESHOLD = 0.004
MIN_AREA = 4
MAX_AREA = 5000
BINS = 16
CANONICAL_ANGLES = (0, 45, 90, 135)


@dataclass(frozen=True)
class Dot:
    x: float
    y: float
    r: float
    color: str
    alpha: float
    role: str = "organ"


# ---- colour ---------------------------------------------------------------------------------------------------------

def hex_to_rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.strip()
    if len(h) != 7 or h[0] != "#":
        raise ValueError(f"not a #rrggbb colour: {hex_}")
    n = int(h[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _linear(c: float) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def lch_of(hex_: str) -> tuple[float, float, float]:
    L, a, b = rgb_to_oklab(hex_to_rgb(hex_))
    return L, math.hypot(a, b), (math.degrees(math.atan2(b, a)) + 360) % 360


def composite(fg: tuple[float, float, float], alpha: float, bg: tuple[float, float, float]) -> tuple[float, float, float]:
    a = min(1.0, max(0.0, alpha))
    return tuple(f * a + g * (1 - a) for f, g in zip(fg, bg, strict=True))  # type: ignore[return-value]


def dot_delta_l(d: Dot, ground: str) -> float:
    bg = hex_to_rgb(ground)
    return abs(rgb_to_oklab(composite(hex_to_rgb(d.color), d.alpha, bg))[0] - rgb_to_oklab(bg)[0])


def hue_distance(a: float, b: float) -> float:
    d = abs((a - b) % 360)
    return min(d, 360 - d)


# ---- statistics -----------------------------------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    if not xs:
        raise ValueError("mean of empty sample")
    return sum(xs) / len(xs)


def percentile(xs: list[float], p: float) -> float:
    """Nearest-rank percentile, p in (0, 100]."""
    if not xs:
        raise ValueError("percentile of empty sample")
    s = sorted(xs)
    rank = math.ceil((p / 100) * len(s))
    return s[min(len(s), max(1, rank)) - 1]


def median(xs: list[float]) -> float:
    if not xs:
        raise ValueError("median of empty sample")
    s = sorted(xs)
    mid = len(s) >> 1
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def visible(dots: list[Dot]) -> list[Dot]:
    return [d for d in dots if d.alpha > 0 and d.r > 0]


def lightness_stats(dots: list[Dot], ground: str) -> dict[str, float]:
    v = [dot_delta_l(d, ground) for d in visible(dots)]
    if not v:
        return {"mean": 0.0, "p95": 0.0, "n": 0}
    return {"mean": mean(v), "p95": percentile(v, 95), "n": len(v)}


def coverage(dots: list[Dot], width: float, height: float) -> float:
    return sum(math.pi * d.r * d.r for d in visible(dots)) / (width * height)


def mean_chroma(dots: list[Dot]) -> float:
    v = visible(dots)
    return mean([lch_of(d.color)[1] for d in v]) if v else 0.0


# ---- banding --------------------------------------------------------------------------------------------------------

def _profile(dots: list[Dot], ground: str, width: float, height: float, angle: float, bins: int) -> list[float | None]:
    th = math.radians(angle)
    ux, uy = math.cos(th), math.sin(th)
    corners = [x * ux + y * uy for x, y in ((0, 0), (width, 0), (0, height), (width, height))]
    lo, hi = min(corners), max(corners)
    total, count = [0.0] * bins, [0] * bins
    for d in dots:
        if d.role != "organ":
            continue
        i = min(bins - 1, max(0, math.floor(((d.x * ux + d.y * uy - lo) / (hi - lo)) * bins)))
        total[i] += dot_delta_l(d, ground) if d.alpha > 0 and d.r > 0 else 0.0
        count[i] += 1
    return [total[i] / count[i] if count[i] else None for i in range(bins)]


def band_spectrum(dots: list[Dot], ground: str, width: float, height: float, angle: float, bins: int = BINS) -> list[float]:
    filled = _profile(dots, ground, width, height, angle, bins)
    known = [v for v in filled if v is not None]
    mu = mean(known) if known else 0.0
    if mu <= 0:
        return [0.0] * (bins // 2 - 1)
    prof = [mu if v is None else v for v in filled]
    out = []
    for k in range(1, bins // 2):
        re = sum(prof[n] * math.cos(2 * math.pi * k * n / bins) for n in range(bins))
        im = -sum(prof[n] * math.sin(2 * math.pi * k * n / bins) for n in range(bins))
        out.append(2 * math.hypot(re, im) / (bins * mu))
    return out


def banding(dots: list[Dot], ground: str, width: float, height: float) -> dict[str, float]:
    best = {"lowK": 0.0, "highK": 0.0, "angle": 0}
    for a in CANONICAL_ANGLES:
        s = band_spectrum(dots, ground, width, height, a)
        low, high = math.hypot(s[0], s[1]), math.hypot(*s[2:])
        if max(low, high) > max(best["lowK"], best["highK"]):
            best = {"lowK": low, "highK": high, "angle": a}
    return best


def spot_ratios(dots: list[Dot]) -> dict[str, float]:
    v = visible(dots)
    organs = [d.r for d in v if d.role == "organ"]
    if not organs:
        return {"first": 0.0, "second": 0.0}
    med = median(organs)
    radii = sorted((d.r for d in v), reverse=True)
    return {"first": radii[0] / med, "second": (radii[1] if len(radii) > 1 else 0.0) / med}


def organ_key(dots: list[Dot]) -> str:
    return ";".join(sorted(f"{d.x:.2f},{d.y:.2f}" for d in dots if d.role == "organ"))


# ---- PNG (stdlib only) ----------------------------------------------------------------------------------------------

PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


class PngError(ValueError):
    """The file is not a PNG this reader supports (8-bit, non-interlaced, colour type 0/2/4/6)."""


@dataclass(frozen=True)
class Image:
    width: int
    height: int
    rows: list[bytes]   # RGB, 3 bytes per pixel, one entry per scanline

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        row = self.rows[y]
        return row[3 * x], row[3 * x + 1], row[3 * x + 2]


def _chunks(data: bytes):
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise PngError("truncated chunk")
        yield kind, body
        pos += 12 + length


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _unfilter_row(kind: int, line: bytearray, prev: bytearray, bpp: int) -> bytearray:
    if kind == 0:
        return line
    for i in range(len(line)):
        left = line[i - bpp] if i >= bpp else 0
        up = prev[i]
        upleft = prev[i - bpp] if i >= bpp else 0
        add = (0, left, up, (left + up) // 2, _paeth(left, up, upleft))[kind]
        line[i] = (line[i] + add) & 255
    return line


def _to_rgb(line: bytearray, ctype: int, width: int) -> bytes:
    if ctype == 2:
        return bytes(line)
    out = bytearray(3 * width)
    step = _CHANNELS[ctype]
    for x in range(width):
        if ctype in (0, 4):
            out[3 * x] = out[3 * x + 1] = out[3 * x + 2] = line[step * x]
        else:
            out[3 * x:3 * x + 3] = line[step * x:step * x + 3]
    return bytes(out)


def _parse_png(data: bytes) -> tuple[tuple, bytes]:
    if not data.startswith(PNG_SIG):
        raise PngError("not a PNG (bad signature)")
    header, idat = None, bytearray()
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
    if header is None:
        raise PngError("no IHDR")
    return header, bytes(idat)


def read_png(path: Path) -> Image:
    header, idat = _parse_png(Path(path).read_bytes())
    width, height, depth, ctype, _comp, _filt, interlace = header
    if depth != 8 or ctype not in _CHANNELS or interlace != 0 or width < 1 or height < 1:
        raise PngError(f"unsupported PNG (depth {depth}, colour type {ctype}, interlace {interlace})")
    try:
        raw = zlib.decompress(idat)
    except zlib.error as e:
        raise PngError(f"corrupt image data: {e}") from e
    stride, bpp = width * _CHANNELS[ctype], _CHANNELS[ctype]
    if len(raw) != height * (stride + 1):
        raise PngError("image data has the wrong length")
    rows, prev = [], bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        line = _unfilter_row(raw[base], bytearray(raw[base + 1:base + 1 + stride]), prev, bpp)
        rows.append(_to_rgb(line, ctype, width))
        prev = line
    return Image(width, height, rows)


def write_png(path: Path, width: int, height: int, rows: list[bytes]) -> None:
    """Minimal 8-bit RGB writer (used by tests and by the harness to emit stills)."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    Path(path).write_bytes(PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ---- pixels → dots --------------------------------------------------------------------------------------------------

Rect = tuple[int, int, int, int]   # x, y, w, h


def _inside(x: int, y: int, rects: list[Rect]) -> bool:
    return any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in rects)


def _ground_of(img: Image, region: Rect, exclude: list[Rect]) -> tuple[int, int, int]:
    rx, ry, rw, rh = region
    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(ry, ry + rh):
        row = img.rows[y]
        for x in range(rx, rx + rw):
            if not exclude or not _inside(x, y, exclude):
                counts[(row[3 * x], row[3 * x + 1], row[3 * x + 2])] += 1
    if not counts:
        raise ValueError("the region is entirely excluded")
    return counts.most_common(1)[0][0]


def _ink_mask(img: Image, region: Rect, exclude: list[Rect]) -> tuple[str, dict[tuple[int, int], tuple[int, int, int]]]:
    rx, ry, rw, rh = region
    ground = _ground_of(img, region, exclude)
    gl = rgb_to_oklab(ground)[0]
    memo: dict[tuple[int, int, int], float] = {}
    ink: dict[tuple[int, int], tuple[int, int, int]] = {}
    for y in range(ry, ry + rh):
        row = img.rows[y]
        for x in range(rx, rx + rw):
            px = (row[3 * x], row[3 * x + 1], row[3 * x + 2])
            if px == ground or (exclude and _inside(x, y, exclude)):
                continue
            if px not in memo:
                memo[px] = abs(rgb_to_oklab(px)[0] - gl)
            if memo[px] >= INK_THRESHOLD:
                ink[(x, y)] = px
    return rgb_to_hex(ground), ink


def _components(ink: dict[tuple[int, int], tuple[int, int, int]]) -> list[list[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    out = []
    for start in ink:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            x, y = stack.pop()
            comp.append((x, y))
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in ink and n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(comp)
    return out


def detect_organs(img: Image, region: Rect, exclude: list[Rect] | None = None) -> tuple[list[Dot], str]:
    """The organs visible in `region` of a still, and the ground colour they sit on. Coordinates are region-relative."""
    rx, ry, rw, rh = region
    if rx < 0 or ry < 0 or rw < 1 or rh < 1 or rx + rw > img.width or ry + rh > img.height:
        raise ValueError(f"region {region} is outside the {img.width}×{img.height} image")
    ground, ink = _ink_mask(img, region, exclude or [])
    dots = []
    for comp in _components(ink):
        if not MIN_AREA <= len(comp) <= MAX_AREA:
            continue
        n = len(comp)
        cx = sum(x for x, _ in comp) / n - rx
        cy = sum(y for _, y in comp) / n - ry
        mean_rgb = tuple(sum(ink[p][c] for p in comp) / n for c in range(3))
        dots.append(Dot(cx, cy, math.sqrt(n / math.pi), rgb_to_hex(mean_rgb), 1.0, "organ"))
    return sorted(dots, key=lambda d: (d.x, d.y)), ground


def field_metrics(img: Image, region: Rect, exclude: list[Rect] | None = None) -> dict[str, float]:
    """The numbers the manifest's `field_pixels.<state>` carries, from raw pixels."""
    dots, ground = detect_organs(img, region, exclude)
    if not dots:
        return {"organs_detected": 0, "p95_dL": 0.0, "mean_dL": 0.0, "lowK": 0.0, "highK": 0.0}
    st = lightness_stats(dots, ground)
    b = banding(dots, ground, region[2], region[3])
    return {"organs_detected": len(dots), "p95_dL": st["p95"], "mean_dL": st["mean"], "lowK": b["lowK"], "highK": b["highK"]}
