// Direction B — "disruptive / flamboyant graphic" (Metasepia pfefferi read as graphic design).
// Pure ESM: no imports, timers or I/O. Hard-edged flat colour only: structure, not shading.
// Hue = identity (ground colour, OKLCh at session.hue_deg). Amber / red only on alarm states.

export const meta = {
  id: 'b-disruptive',
  name: 'Disruptive graphic',
  biology:
    'Metasepia pfefferi display as graphic design: idle=regular dot lattice (resting skin papillae), working=one hard-edged dark mass sweeping (passing cloud), ' +
    'review=blocky disruptive camouflage patches, needs-you=thick zebra bands + amber ring eyespots, fault=full deimatic blanch + red frame + eyespots, unknown=neutral diagonal hatch',
  maxColorsWorking: 48,
  fps: 4,
};

// ---------- colour (OKLCh -> sRGB, chroma reduced into gamut) ----------
const lin2s = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  for (let c = C; c >= 0; c -= 0.004) {
    const a = c * Math.cos(h), b = c * Math.sin(h);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
    const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
    const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
    if ([r, g, bl].every((v) => v >= -0.0005 && v <= 1.0005)) {
      return [r, g, bl].map((v) => Math.round(255 * lin2s(Math.min(1, Math.max(0, v)))));
    }
  }
  return [128, 128, 128];
}
const hex = (c) => '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
const unhex = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));

const INK = [20, 22, 26];
const PAPER = [244, 242, 236];
const AMBER = [255, 176, 0];
const RED = [208, 16, 42];
const GREY_A = [58, 60, 64];
const GREY_B = [116, 118, 122];

const PLATE = {
  alarmInput: { bg: '#ffb000', fg: '#1a1200' },
  alarmError: { bg: '#b3001b', fg: '#ffffff' },
  unknown: { bg: '#d8d8d8', fg: '#111111' },
  nameNeutral: { bg: '#2a2a2a', fg: '#ffffff' },
};
const identPlate = (hue) => oklch(0.3, 0.07, hue);

function ident(hue) {
  return { ground: oklch(0.52, 0.13, hue), light: oklch(0.78, 0.11, hue), dark: oklch(0.34, 0.09, hue) };
}

// ---------- helpers ----------
function hs(a, b, c) {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263) + Math.imul(c | 0, 2246822519)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

// Eyespot: amber ring + ink pupil (ring/pupil colours supplied). (cx,cy) centre, rx,ry radii in grid px.
function eye(gx, gy, cx, cy, rx, ry, ring, pupil, gh) {
  const nx = (gx - cx) / rx, ny = (gy - cy) / ry;
  const d = Math.sqrt(nx * nx + ny * ny);
  if (d > 1) return null;
  const pr = gh < 4 ? 0.62 : 0.42;
  return d < pr ? pupil : ring;
}

// ---------- the six patterns, in grid units (gx, gy) over gw x gh ----------
function patternFn(state, session, gw, gh, t, opts) {
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const seed = ((session && session.idx) | 0) + 11;
  const P = hue === null ? null : ident(hue);
  const eyeRy = Math.max(1, gh / 2), eyeRx = Math.max(2.5, Math.min(eyeRy * 2.2, gw / 8));
  const eyeCx = (k, n) => Math.round(((k + 0.5) * gw) / n);

  if (state === 'idle' && P) {
    // regular dot lattice: ink dots on identity ground, staggered every other row
    return (gx, gy) => ((gx + (gy % 2 ? 2 : 0)) % 4 === 0 ? INK : P.ground);
  }
  if (state === 'working' && P) {
    const massW = Math.max(4, Math.round(gw * 0.38));
    const cycle = gw + massW;
    const tt = opts && opts.reducedMotion ? null : Math.floor((t || 0) * 4) / 4;
    const base = Math.round(gw * 0.3 + massW); // mass is on-screen at t=0 and in the static (reducedMotion) frame
    const lead = tt === null ? base : Math.floor((base + (tt * cycle) / 10) % cycle);
    const stag = [0, 2, -1, 1];
    return (gx, gy) => {
      const e = lead + (gh > 1 ? stag[gy % 4] : 0); // leading edge (right side), stepped
      const x0 = e - massW;
      if (gx === e - 1 && gx >= 0) return P.light; // crisp bright leading edge
      return gx >= x0 && gx < e - 1 ? INK : P.ground;
    };
  }
  if (state === 'review' && P) {
    // blocky camouflage: per-row runs of 2..5 px, 3 identity tones, never two equal neighbours
    const bh = gh >= 6 ? 2 : 1;
    const tones = [P.ground, P.light, P.dark];
    const bands = [];
    for (let by = 0; by <= Math.floor((gh - 1) / bh); by++) {
      const row = new Array(gw);
      let x = 0, prev = -1;
      while (x < gw) {
        const len = 2 + Math.floor(hs(by, x, seed) * 4);
        let tn = Math.floor(hs(x, by, seed + 7) * 3);
        if (tn === prev) tn = (tn + 1) % 3;
        for (let k = 0; k < len && x + k < gw; k++) row[x + k] = tones[tn];
        x += len;
        prev = tn;
      }
      bands.push(row);
    }
    return (gx, gy) => bands[Math.floor(gy / bh)][gx];
  }
  if (state === 'needs-you' && P) {
    const n = Math.max(2, Math.min(5, Math.floor(gw / 14)));
    const eyes = [];
    for (let k = 0; k < n; k++) eyes.push(eyeCx(k, n) + (gw > 40 ? 6 : 0));
    return (gx, gy) => {
      for (const cx of eyes) {
        const c = eye(gx, gy, cx, (gh - 1) / 2, eyeRx, eyeRy, AMBER, INK, gh);
        if (c) return c;
      }
      return gx % 5 < 3 ? P.ground : INK; // thick vertical zebra, identity > ink so identity still reads
    };
  }
  if (state === 'fault') {
    const n = Math.max(2, Math.min(4, Math.floor(gw / 16)));
    const eyes = [];
    for (let k = 0; k < n; k++) eyes.push(eyeCx(k, n) + (gw > 40 ? 6 : 0));
    const full = gh >= 6;
    const cap = Math.max(2, Math.round(gw / 40));
    return (gx, gy) => {
      for (const cx of eyes) {
        const c = eye(gx, gy, cx, (gh - 1) / 2, eyeRx, eyeRy, RED, INK, gh);
        if (c) return c;
      }
      if (full && (gy === 0 || gy === gh - 1 || gx === 0 || gx === gw - 1)) return RED;
      if (!full && (gx < cap || gx >= gw - cap)) return RED;
      return PAPER; // blanch dominates the tile
    };
  }
  // unknown / degraded / any state with no identity hue: neutral diagonal hatch
  return (gx, gy) => ((gx + gy) % 4 < 2 ? GREY_A : GREY_B);
}

// ---------- plates + text (literal, durable) ----------
function layout(scale, state, session, w, h) {
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const items = [];
  if (state === 'needs-you' && session.alarm_text) items.push({ str: session.alarm_text, ...PLATE.alarmInput });
  else if (state === 'fault' && session.alarm_text) items.push({ str: session.alarm_text, ...PLATE.alarmError });
  else if (state === 'unknown' || !hue) items.push({ str: '?', ...PLATE.unknown });
  const nm = session && session.name ? session.name : '';
  if (nm) items.push({ str: nm, bg: hue === null ? PLATE.nameNeutral.bg : hex(identPlate(hue)), fg: '#ffffff' });
  return items;
}

export function paint({ scale, w, h, state, session, t, opts }) {
  const px = new Uint8ClampedArray(w * h * 4);
  const xl = scale === 'XL';
  const u = xl ? Math.max(2, Math.ceil(h / 32)) : 1;
  const gw = Math.ceil(w / u), gh = Math.ceil(h / u);
  const fn = patternFn(state, session, gw, gh, t, opts);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const c = fn(Math.floor(x / u), Math.floor(y / u));
      const i = (y * w + x) * 4;
      px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255;
    }
  const items = layout(scale, state, session, w, h);
  const text = [];
  // plate geometry: M/S cells (1 px per cell column; text row 0 covers 2 px rows on the half rung, 1 on bg);
  // XL in CSS px (10 px per char, 32 px tall plate)
  const pr = xl ? Math.min(h, 32) : h >= 4 ? 2 : 1;
  const cw = xl ? 10 : 1, padc = xl ? 10 : 1;
  let x = scale === 'S' ? Math.min(6, Math.max(0, w - 3)) : 0;
  items.forEach((it, k) => {
    const widthPx = it.str.length * cw + 2 * padc;
    if (k > 0 && x + widthPx > w) return; // priority: alarm / '?' first, then name if it fits
    const bg = unhex(it.bg);
    for (let yy = 0; yy < pr; yy++)
      for (let xx = x; xx < Math.min(w, x + widthPx); xx++) {
        const i = (yy * w + xx) * 4;
        px[i] = bg[0]; px[i + 1] = bg[1]; px[i + 2] = bg[2];
      }
    text.push(xl ? { x: x + padc, y: 8, str: it.str, fg: it.fg, bg: it.bg } : { x: x + padc, y: 0, str: it.str, fg: it.fg, bg: it.bg });
    x += widthPx;
  });
  return { pixels: px, text };
}

export function authoredPairs() {
  const pairs = [
    { fg: PLATE.alarmInput.fg, bg: PLATE.alarmInput.bg, where: 'M/S/XL alarm text (needs-you)' },
    { fg: PLATE.alarmError.fg, bg: PLATE.alarmError.bg, where: 'M/S/XL alarm text (fault)' },
    { fg: PLATE.unknown.fg, bg: PLATE.unknown.bg, where: 'M/S/XL unknown ?' },
    { fg: PLATE.nameNeutral.fg, bg: PLATE.nameNeutral.bg, where: 'M/S/XL name (unbound)' },
  ];
  for (let h = 110; h < 340; h += 15) pairs.push({ fg: '#ffffff', bg: hex(identPlate(h)), where: `name plate @hue ${h}` });
  return pairs;
}
