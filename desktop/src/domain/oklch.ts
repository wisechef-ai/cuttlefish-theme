// OKLab/OKLCh <-> sRGB, Ottosson 2020. The sRGB direction is ported from origin/v22
// packages/core/domain/oklch.ts; the OKLab direction uses the same published matrices the
// acceptance instruments use, so a dot's measured |dL| here matches what renders.
// Pure maths: no I/O, no clock, no randomness.

export interface Rgb { r: number; g: number; b: number }   // 0..255 sRGB
export interface Lab { L: number; a: number; b: number }   // OKLab
export interface Lch { L: number; C: number; h: number }   // OKLCH, h in degrees [0, 360)

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/** OKLCh -> sRGB 0..255, clipped to gamut, rounded to 8-bit codes. */
export function oklchToRgb(L: number, C: number, hDeg: number): Rgb {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  return oklabToRgb(L, a, b);
}

/** OKLab -> sRGB 0..255 (Ottosson's matrices), clipped and rounded like a CSS colour. */
export function oklabToRgb(L: number, a: number, b: number): Rgb {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  const enc = (c: number): number => {
    const v = clamp01(c);
    return Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
  };
  return {
    r: enc(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    g: enc(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    b: enc(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
  };
}

const toLinear = (c: number): number => {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
};

/** sRGB 0..255 -> OKLab (continuous codes; compositing happens here before this). */
export function rgbToOklab({ r, g, b }: Rgb): Lab {
  const R = toLinear(r), G = toLinear(g), B = toLinear(b);
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  return {
    L: 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
  };
}

export function oklabToLch({ L, a, b }: Lab): Lch {
  const h = (Math.atan2(b, a) * 180) / Math.PI;
  return { L, C: Math.hypot(a, b), h: (h + 360) % 360 };
}

export function hexToRgb(hex: string): Rgb {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgbToHex({ r, g, b }: Rgb): string {
  const h = (v: number): string => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

/** OKLCh -> '#rrggbb'. */
export const oklchToHex = (L: number, C: number, hDeg: number): string => rgbToHex(oklchToRgb(L, C, hDeg));

/** A ground colour's OKLab appearance: everything about placement derives from its lightness. */
export function hexToLab(hex: string): Lab {
  return rgbToOklab(hexToRgb(hex));
}

/** Source-over compositing in sRGB codes (what a browser does for a non-blended layer). */
export function composite(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  const a = clamp01(alpha);
  return { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a) };
}

/** |dL| (OKLab) between a pigment at `alpha` over `bg`, and the bare ground. */
export function deltaLOf(fg: Rgb, alpha: number, bgRgb: Rgb, bgL: number): number {
  return Math.abs(rgbToOklab(composite(fg, alpha, bgRgb)).L - bgL);
}
