// Direction D "dots": a pure port of the P1 oracle design/directions/d-dots/direction.mjs `paint`.
// A lattice of coloured dots on one plain ground. hue = identity, which dots are open/closed = state.
// ORACLE RULE: test/pattern.oracle.test.ts requires byte-identical pixels and text against the oracle
// for every P1 matrix scene. Do not "improve" this file without changing the oracle (P4 owns eyespot
// anti-aliasing and chip label coverage). Pure: no clock (the frame `step` is passed in), no randomness.
import { oklch, type RGB } from './oklch.ts';
import { TOKENS as T } from './tokens.ts';

export type Scale = 'XL' | 'M' | 'S';
export type Look = 'idle' | 'working' | 'review' | 'needs-you' | 'fault' | 'unknown';
export interface TextRun { x: number; y: number; str: string; fg: string; bg: string }
export interface Painted { pixels: Uint8ClampedArray; text: TextRun[] }
export interface PaintArgs {
  scale: Scale;
  w: number;
  h: number;
  look: Look | string;
  /** Identity hue in degrees, or null/undefined when there is no binding (degraded). */
  hueDeg: number | null | undefined;
  name: string;
  alarmText: string | null | undefined;
  /** Working-cloud frame index = floor(t * 4); the caller owns time. */
  step: number;
  reducedMotion: boolean;
}

// Tokens that tokens.json documents only in prose (fault blanch, unknown grey) live here.
export const BLANCH = { L: 0.9, C: 0.035 };
export const GREY = { L: 0.6, C: 0 };
const GROUND: RGB = [...T.ground.rgb] as RGB;
const AMBER: RGB = [...T.alarm.amber.rgb] as RGB;
const RED: RGB = [...T.alarm.red.rgb] as RGB;
const INK = T.text_pairs[0].fg, PLATE = T.text_pairs[0].bg;
const ALARM_FG: Record<string, string> = { 'needs-you': T.text_pairs[1].fg, fault: T.text_pairs[2].fg };
const ALARM_BG: Record<string, string> = { 'needs-you': T.text_pairs[1].bg, fault: T.text_pairs[2].bg };

interface Colors { dots: RGB[]; blanch: RGB; grey: RGB }
interface DotLook { open: number; tone: RGB }

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

// Deterministic hash -> [0, 1).
function hash(i: number, j: number, k = 0): number {
  let n = (i * 374761393 + j * 668265263 + k * 2147483647) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}

// Smooth value noise for the mottle blotches.
function vnoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed), c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

// One dot's look. (c, r) are dot coords, (cols, rows) the lattice size.
function dotLook(c: number, r: number, cols: number, rows: number, look: string, step: number, colors: Colors, seed: number, kind: Scale): DotLook {
  const j = hash(c, r, seed);
  const shade = colors.dots[Math.floor(j * 3) % 3];
  switch (look) {
    case 'idle':
      return { open: j < 0.18 ? 0 : 1, tone: shade };
    case 'working': {
      // A band of closed dots drifts left to right one dot per frame (<= 4 fps): the passing cloud.
      // (Woo 2023, the passing-cloud display of cuttlefish skin, is the plan's reference for this motif;
      // the parameters below are the P1 oracle's, tuned on rendered pixels, not taken from the paper.)
      const narrow = kind === 'M' && cols <= 30;
      const period = kind === 'S' ? Math.max(3, cols) : narrow ? 6 : kind === 'M' ? 16 : 14;
      const half = kind === 'S' ? 0 : narrow ? 1 : kind === 'M' ? 2 : 3;
      const pos = ((c + Math.floor(r * 0.5) - step) % period + period) % period;
      const d = Math.min(pos, period - pos);
      if (d <= half) return { open: d === half && half > 0 ? 0.5 : 0, tone: shade };
      return { open: j < 0.1 ? 0 : 1, tone: shade };
    }
    case 'review': {
      const k = kind === 'XL' ? 5 : 3;
      const n = vnoise(c / k, r / (kind === 'XL' ? k : 1.2), seed + 7);
      if (n < 0.38) return { open: 0, tone: shade };
      return { open: n < 0.5 ? 0.5 : 1, tone: n > 0.66 ? colors.dots[2] : colors.dots[0] };
    }
    case 'needs-you': {
      const band = kind === 'XL' ? Math.floor((c + (r & 1) * 0.5 + r * 0.5) / 2) : Math.floor(c / 2);
      return band % 2 === 0 ? { open: 1, tone: colors.dots[2] } : { open: 0, tone: shade };
    }
    case 'fault': {
      const edge = kind === 'XL' ? 2 : 1;
      const onEdge = c < edge || c >= cols - edge || (kind === 'XL' && (r < edge || r >= rows - edge));
      if (onEdge) return { open: 1, tone: RED };
      return { open: j < 0.06 ? 0.5 : 1, tone: colors.blanch };
    }
    default: // unknown / degraded: sparse grey dots on a diagonal, no identity claim
      return { open: (c + r) % 3 === 0 ? 1 : 0, tone: colors.grey };
  }
}

function eyespots(kind: Scale, w: number, h: number): { x: number; y: number; r: number }[] {
  if (kind === 'XL') {
    const r = Math.max(4, Math.min(w, h) * 0.09);
    return [{ x: w * 0.3, y: h * 0.5, r }, { x: w * 0.7, y: h * 0.5, r }];
  }
  if (w <= 8) return [{ x: w - 1, y: 0, r: 0 }];
  return [{ x: Math.floor(w * 0.35), y: Math.floor((h - 1) / 2), r: 0 }, { x: Math.floor(w * 0.65), y: Math.floor((h - 1) / 2), r: 0 }];
}

function put(px: Uint8ClampedArray, i: number, c: RGB): void { px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255; }
const mix = (a: RGB, b: RGB, k: number): RGB => [0, 1, 2].map(n => Math.round(a[n] + (b[n] - a[n]) * k)) as RGB;

export function paint(a: PaintArgs): Painted {
  const { scale, w, h } = a;
  const degraded = a.hueDeg == null;
  const look = degraded ? 'unknown' : a.look;
  const hue = degraded ? 0 : (a.hueDeg as number);
  const colors: Colors = {
    dots: T.identity.dot_lightness.map(L => oklch(L, T.identity.dot_chroma, hue)),
    blanch: oklch(BLANCH.L, BLANCH.C, hue),
    grey: oklch(GREY.L, GREY.C, 0),
  };
  const moving = look === 'working' && !a.reducedMotion;
  const step = moving ? a.step : 0;                       // one dot per 0.25 s: <= 4 fps
  const seed = degraded ? 1 : Math.round(hue * 10);
  const G = GROUND;
  const px = new Uint8ClampedArray(w * h * 4);
  const kind: Scale = scale === 'XL' ? 'XL' : (w <= 8 ? 'S' : 'M');

  if (scale === 'XL') {
    const P = T.scales.XL.pitch_px, RP = P * 0.866, R = P * T.scales.XL.dot_radius_ratio;
    const rows = Math.ceil(h / RP) + 1, cols = Math.ceil(w / P) + 1;
    const spots = look === 'needs-you' ? eyespots('XL', w, h) : [];
    const levels = T.scales.XL.coverage_levels - 1;      // 4 coverage levels: a soft, few-colour edge
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let col = G, best = 0;
        const r0 = Math.round(y / RP);
        for (let r = r0 - 1; r <= r0 + 1; r++) {
          const off = (r & 1) ? P / 2 : 0;
          const c0 = Math.round((x - off) / P);
          for (let c = c0 - 1; c <= c0 + 1; c++) {
            const d = dotLook(c, r, cols, rows, look, step, colors, seed, 'XL');
            if (d.open <= 0) continue;
            const rad = d.open >= 1 ? R : R * 0.55;
            const dist = Math.hypot(x - (c * P + off), y - r * RP);
            const cov = Math.round(clamp01(rad - dist + 0.5) * levels) / levels;
            if (cov > best) { best = cov; col = mix(G, d.tone, cov); }
          }
        }
        for (const s of spots) {
          const d = Math.hypot(x - s.x, y - s.y);
          if (d < s.r * 0.35) col = G;                    // pupil
          else if (d < s.r) col = AMBER;
        }
        put(px, (y * w + x) * 4, col);
      }
    }
  } else {
    const spots = look === 'needs-you' ? eyespots(kind, w, h) : [];
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const d = dotLook(x, y, w, h, look, step, colors, seed, kind);
        let col = d.open >= 1 ? d.tone : d.open > 0 ? mix(G, d.tone, 0.5) : G;
        if (spots.some(s => s.x === x && s.y === y)) col = AMBER;
        put(px, (y * w + x) * 4, col);
      }
    }
  }

  const text: TextRun[] = [];
  const name = degraded ? 'unbound' : a.name;
  const alarm = look === 'unknown' ? '?' : a.alarmText || null;
  const fg = ALARM_FG[look] ?? INK, bg = ALARM_BG[look] ?? PLATE;
  if (scale === 'XL') {
    text.push({ x: 16, y: 16, str: name, fg: INK, bg: PLATE });
    if (alarm) text.push({ x: 16, y: 48, str: alarm, fg, bg });
  } else if (w > 8) {
    const label = ` ${name} `.slice(0, w);
    const s = alarm ? ` ${alarm} ` : '';
    if (!alarm) text.push({ x: 0, y: 0, str: label, fg: INK, bg: PLATE });
    else if (label.length + s.length <= w) {
      text.push({ x: 0, y: 0, str: label, fg: INK, bg: PLATE });
      text.push({ x: w - s.length, y: 0, str: s, fg, bg });
    } else {
      text.push({ x: 0, y: 0, str: s.slice(0, w), fg, bg });   // too narrow for both: the alarm wins
    }
  } // desktop S swatch (w <= 8): no text, the sidebar row carries the name
  return { pixels: px, text };
}
