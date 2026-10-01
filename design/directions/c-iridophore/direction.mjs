// Direction C: "iridophore night". Pure ESM with no imports, timers or I/O (tools/p1/CONTRACT.md §2).
//
// The look is layered. A deep mantle base carries the session's identity hue (OKLCh). Over it sits
// a sheen layer of bright, low-chroma highlights (iridophores/leucophores), and a pale fin-edge line
// runs along the bottom (the cuttlefish fin's margin). State is told by the STRUCTURE of the sheen
// layer, never by shading alone, so it survives the bg rung (1×2 px/cell), 256 colours and CVD:
//   idle      stipple: sparse isolated sparkles             (static)
//   working   passing cloud: one wide luminous band drifting (the only animated state; ≤4 fps)
//   review    mottle: cloudy light/dark patches              (static)
//   needs-you zebra: regular sheen/dark vertical bars + amber eyespots + literal alarm text
//   fault     deimatic: whole field blanched bright + red edge glow + literal alarm text
//   unknown   neutral grey diagonal hatch + "?" (no sheen, no identity hue)

export const meta = {
  id: 'c-iridophore',
  name: 'Iridophore night',
  biology:
    'Sepia officinalis/Metasepia: idle = leucophore stipple on dark mantle; working = passing cloud ' +
    '(chromatophore wave read as a sheen band); review = mottle; needs-you = zebra bars + eyespots ' +
    '(Sepia zebra display + Metasepia ocelli); fault = deimatic blanch with flashing margin; ' +
    'unknown = no pattern claimed (neutral hatch). Fin-edge line = the pale fin margin.',
  maxColorsWorking: 48,
  fps: 4,
};

// ---------- colour: OKLCh → sRGB, chroma-only gamut clip (hue is identity, so it never moves) ----------
const lin2srgb = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
function oklabToLinear(L, a, b) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
}
const inGamut = rgb => rgb.every(v => v >= -1e-4 && v <= 1 + 1e-4);
function lch(L, C, h) {
  const r = (h * Math.PI) / 180;
  return [L, C * Math.cos(r), C * Math.sin(r)];
}
function maxChroma(L, h) {
  let lo = 0, hi = 0.4;
  for (let i = 0; i < 24; i++) {
    const c = (lo + hi) / 2;
    if (inGamut(oklabToLinear(...lch(L, c, h)))) lo = c; else hi = c;
  }
  return lo;
}
function labToRgb8([L, a, b]) {
  return oklabToLinear(L, a, b).map(v => Math.round(255 * lin2srgb(Math.min(1, Math.max(0, v)))));
}
// A colour in this direction is an OKLab triple; mixing happens in OKLab (same hue in → same hue out).
function lchClip(L, C, h) {
  return lch(L, Math.min(C, maxChroma(L, h) * 0.98), h);
}
const mix = (p, q, k) => [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k, p[2] + (q[2] - p[2]) * k];

// ---------- fixed (non-identity) colours ----------
const NEUTRAL = {
  hatchGround: [0.27, 0, 0],
  hatchLine: [0.47, 0, 0],
  hatchDeep: [0.20, 0, 0],
};
const AMBER = lch(0.80, 0.16, 70);      // eyespot iris (alarm only)
const AMBER_DEEP = lch(0.58, 0.13, 60);  // eyespot rim (alarm only)
const PUPIL = [0.12, 0, 0];
const RED = lch(0.55, 0.20, 27);         // fault edge glow (alarm only)
const RED_SOFT = lch(0.70, 0.13, 22);

// Text plates. Fixed colours so authoredPairs() is the complete set (G2 contrast table).
const TEXT = {
  name: { fg: '#eef1f5', bg: '#0b0e13' },
  input: { fg: '#1a1000', bg: '#f2a516' },
  error: { fg: '#ffffff', bg: '#b3121e' },
  unknown: { fg: '#0b0e13', bg: '#c9ccd1' },
};

// ---------- identity palette (memoised per hue: pure, no I/O) ----------
const palCache = new Map();
function identityPalette(h) {
  if (palCache.has(h)) return palCache.get(h);
  // Deep base: as dark as the hue allows while still carrying ≥ 0.112 chroma. Blues/violets sit at
  // L .40, the narrow-gamut teals rise to ~.6. That keeps 20 sessions 11.5° apart ≥ ΔE_OK .02 (G2).
  let L = 0.40;
  while (L < 0.64 && maxChroma(L, h) < 0.118) L += 0.01;
  const C = Math.min(0.15, maxChroma(L, h) * 0.97);
  const p = {
    base: lch(L, C, h),
    deep: lchClip(Math.max(0.16, L - 0.2), 0.06, h),
    sheen: lchClip(0.93, 0.045, h),
    light: lchClip(Math.min(0.86, L + 0.3), 0.09, h),
    fin: lchClip(0.86, 0.07, h),
    blanch: lchClip(0.94, 0.02, h),
  };
  palCache.set(h, p);
  return p;
}

// ---------- deterministic hash / value noise ----------
function hash2(x, y, seed) {
  let n = (x * 374761393 + y * 668265263 + seed * 2147483647) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  n ^= n >>> 16;
  return (n >>> 0) / 4294967295;
}
function strSeed(s) {
  let n = 2166136261;
  for (let i = 0; i < s.length; i++) n = Math.imul(n ^ s.charCodeAt(i), 16777619);
  return n >>> 0;
}
const smooth = k => k * k * (3 - 2 * k);
function vnoise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), fx = smooth(x - xi), fy = smooth(y - yi);
  const a = hash2(xi, yi, seed), b = hash2(xi + 1, yi, seed);
  const c = hash2(xi, yi + 1, seed), d = hash2(xi + 1, yi + 1, seed);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

// ---------- geometry per scale ----------
// The pattern is drawn on a grid of "pattern pixels". For M/S, one grid pixel is one logical pixel
// (tall: 10×11 screen px on the half rung, 10×22 on the bg rung). XL is drawn on a 4-px grid.
function geometry(scale, w, h) {
  if (scale === 'XL') {
    const u = Math.max(2, Math.round(Math.min(w, h) / 90));
    return { u, gw: Math.ceil(w / u), gh: Math.ceil(h / u), aspect: 1, xl: true };
  }
  // h ≤ 2 is the bg rung (or a 1-row half mantle): each pixel is about twice as tall as wide.
  return { u: 1, gw: w, gh: h, aspect: h <= 2 ? 2.2 : 1.1, xl: false };
}

// ---------- per-state painters: return an OKLab triple for grid pixel (x, y) ----------
function painterFor(state, session, g, t, opts) {
  const { gw, gh, aspect, xl } = g;
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const seed = strSeed(String((session && (session.lineage_id || session.name)) || 'unbound'));
  const finRows = xl ? Math.max(2, Math.round(gh * 0.035)) : gh >= 3 ? 1 : 0;
  const isFin = y => y >= gh - finRows;

  if (state === 'unknown' || hue === null) {
    // Neutral hatch: thin grey diagonal lines on a dim ground, a darker band at the bottom instead of
    // the fin line (no sheen layer at all = "no pattern claimed"). A session whose identity is still
    // known (stale binding) keeps a dim identity ground so "who" stays findable (plan §1.2); the
    // degraded/no-binding mantle (hue_deg null) is pure grey and claims nothing.
    const period = xl ? 9 : 5;
    const ground = hue === null ? NEUTRAL.hatchGround : lchClip(0.30, 0.05, hue);
    return (x, y) => {
      if (finRows && isFin(y)) return NEUTRAL.hatchDeep;
      const d = Math.round(x + y * (xl ? 1 : aspect)) % period;
      return d === 0 ? NEUTRAL.hatchLine : ground;
    };
  }

  const P = identityPalette(hue);

  if (state === 'idle') {
    // Stipple: sparse isolated sparkles. A sparkle never touches another (checked left/up), so the
    // structure stays "dots", never "patches", even when 256-colour banding merges tones.
    const density = xl ? 0.035 : gw <= 16 ? 0.3 : 0.16;
    const spark = (x, y) => hash2(x, y, seed) < density;
    return (x, y) => {
      if (finRows && isFin(y)) return P.fin;
      if (spark(x, y) && !spark(x - 1, y) && !spark(x, y - 1) && !spark(x - 1, y - 1) && !spark(x + 1, y - 1)) return P.sheen;
      return P.base;
    };
  }

  if (state === 'working') {
    // Passing cloud: one wide luminous band drifting left→right, quantised to 4 fps and 8 levels.
    const tq = opts.reducedMotion ? 0 : Math.floor(t * 4) / 4;
    const bw = xl ? gw * 0.28 : Math.max(8, Math.min(24, gw * 0.2));
    const speed = xl ? gw / 24 : 6; // grid px per second: a few cells/s on the mantle
    const span = gw + 2 * bw;
    const cx = ((tq * speed + gw * 0.3 + bw) % span) - bw;
    const levels = [];
    for (let i = 0; i <= 8; i++) levels.push(mix(P.base, P.light, i / 8));
    return (x, y) => {
      if (finRows && isFin(y)) return P.fin;
      const slant = (gh - 1 - y) * (xl ? 0.35 : 0.6 * aspect);
      const d = Math.abs(x - slant - cx) / (bw / 2);
      if (d >= 1) return P.base;
      const k = Math.cos((d * Math.PI) / 2) ** 2;
      return levels[Math.round(k * 8)];
    };
  }

  if (state === 'review') {
    // Mottle: cloudy patches, three tones (deep / base / light), blobs several cells wide.
    const sx = xl ? 14 : 7, sy = xl ? 14 : 3.2 / aspect;
    return (x, y) => {
      if (finRows && isFin(y)) return P.fin;
      const n = 0.65 * vnoise(x / sx, y / sy, seed) + 0.35 * vnoise(x / (sx * 0.45), y / (sy * 0.45), seed + 7);
      if (n < 0.4) return P.deep;
      if (n > 0.6) return P.light;
      return P.base;
    };
  }

  if (state === 'needs-you') {
    // Zebra: regular vertical bars, sheen vs deep, with amber eyespots (ocelli) every ~30 cells.
    const bar = xl ? 8 : 2;
    const eyeR = xl ? Math.max(5, gh * 0.11) : 1.5;
    const nEyes = xl ? 3 : Math.max(1, Math.round(gw / 30));
    const eyes = [];
    for (let i = 0; i < nEyes; i++) {
      const fx = (i + 0.62) / nEyes;
      eyes.push({ x: Math.round(fx * (gw - 1)), y: xl ? gh * (i % 2 ? 0.62 : 0.38) : (gh - 1) / 2 });
    }
    return (x, y) => {
      for (const e of eyes) {
        const dx = x - e.x, dy = xl ? y - e.y : (y - e.y) * aspect * 0.5;
        const r = Math.hypot(dx, dy);
        if (xl) {
          if (r < eyeR * 0.42) return PUPIL;
          if (r < eyeR * 0.82) return AMBER;
          if (r < eyeR) return AMBER_DEEP;
          if (r < eyeR + 3) return P.deep;
        } else {
          if (Math.abs(dx) <= 0.5 && (gh <= 2 || Math.abs(y - e.y) < 1)) return PUPIL;
          if (Math.abs(dx) <= 1.5) return AMBER;
          if (Math.abs(dx) <= 2.5) return P.deep; // dark moat so the eye never fuses with a bar
        }
      }
      return Math.floor(x / bar) % 2 === 0 ? P.sheen : P.deep;
    };
  }

  if (state === 'fault') {
    // Deimatic: the whole mantle blanches bright; a red glow runs round the margin.
    // On the mantle the glow is the two ends (2 + 1 cells) plus the fin line turning red; the blanched
    // field stays dominant, so "brightest strip" is the cue even with red removed (CVD / 256).
    if (xl) {
      const e = Math.max(6, Math.round(gh * 0.08));
      return (x, y) => {
        const d = Math.min(x, gw - 1 - x, y, gh - 1 - y);
        if (d < e * 0.5) return RED;
        if (d < e) return RED_SOFT;
        return P.blanch;
      };
    }
    return (x, y) => {
      const d = Math.min(x, gw - 1 - x);
      if (d < 2) return RED;
      if (d < 3) return RED_SOFT;
      if (finRows && isFin(y)) return RED;
      return P.blanch;
    };
  }

  return () => NEUTRAL.hatchGround;
}

// ---------- labels ----------
function labels(scale, w, h, state, session) {
  const name = (session && session.name) || 'unbound';
  const alarm = session && session.alarm_text;
  const plates = [];
  if (state === 'needs-you' && alarm) plates.push({ str: ` ${alarm} `, ...TEXT.input });
  else if (state === 'fault' && alarm) plates.push({ str: ` ${alarm} `, ...TEXT.error });
  else if (state === 'unknown' || !session || session.hue_deg === null) plates.push({ str: ' ? ', ...TEXT.unknown });
  plates.push({ str: ` ${name} `, ...TEXT.name });

  const out = [];
  if (scale === 'XL') {
    // CSS px: a stacked caption block, top-left.
    let y = 24;
    for (const p of plates) { out.push({ x: 24, y, str: p.str, fg: p.fg, bg: p.bg }); y += 28; }
    return out;
  }
  // Cell coordinates, row 0 (valid on every rung and the 1-row mantle). Pattern stays visible on the
  // remaining columns and, on 2-row mantles, the whole second row. S pills can't fit the full text,
  // so they keep the alarm/marker plate verbatim and then the name (the host clips the pill).
  let x = scale === 'M' ? 1 : 0;
  for (const p of plates) {
    let str = p.str;
    if (scale === 'M' && x + str.length > w) str = str.trim();
    if (scale === 'M' && x + str.length > w) break;
    out.push({ x, y: 0, str, fg: p.fg, bg: p.bg });
    x += str.length;
  }
  return out;
}

export function paint({ scale, w, h, state, session, t = 0, opts = {} }) {
  const g = geometry(scale, w, h);
  const fn = painterFor(state, session, g, t, opts || {});
  const pixels = new Uint8ClampedArray(w * h * 4);
  // Resolve each distinct OKLab triple once (also keeps the working palette exact).
  const rgbCache = new Map();
  const row = new Array(g.gw);
  for (let gy = 0; gy < g.gh; gy++) {
    for (let gx = 0; gx < g.gw; gx++) {
      const lab = fn(gx, gy);
      let rgb = rgbCache.get(lab);
      if (!rgb) { rgb = labToRgb8(lab); rgbCache.set(lab, rgb); }
      row[gx] = rgb;
    }
    const y0 = gy * g.u, y1 = Math.min(h, y0 + g.u);
    for (let y = y0; y < y1; y++) {
      for (let x = 0; x < w; x++) {
        const rgb = row[Math.min(g.gw - 1, Math.floor(x / g.u))];
        const i = (y * w + x) * 4;
        pixels[i] = rgb[0]; pixels[i + 1] = rgb[1]; pixels[i + 2] = rgb[2]; pixels[i + 3] = 255;
      }
    }
  }
  return { pixels, text: labels(scale, w, h, state, session) };
}

export function authoredPairs() {
  return [
    { ...TEXT.name, where: 'M/S/XL session name plate (every state)' },
    { ...TEXT.input, where: 'M/S/XL needs-you alarm plate (INPUT …)' },
    { ...TEXT.error, where: 'M/S/XL fault alarm plate (ERROR …)' },
    { ...TEXT.unknown, where: 'M/S/XL unknown / unbound "?" plate' },
  ];
}
