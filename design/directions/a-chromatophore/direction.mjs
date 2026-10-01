// Direction A — "chromatophore field". Pure ESM: no imports, no timers, no I/O (CONTRACT §2).
//
// Every logical pixel (XL: every 8-px cell) is a pigment sac whose expansion e∈[0,1] is read as
// one of three identity tones over a pale, neutral leucophore ground. State = which expansion
// field is painted; identity = the session hue in OKLCh; amber/red appear only on alarm states.

export const meta = {
  id: 'a-chromatophore',
  name: 'Chromatophore field',
  biology: 'Sepia officinalis skin: idle=sparse expanded sacs (stipple), working=passing-cloud band, review=mottle, '
    + 'needs-you=zebra bars + two amber eyespots (Metasepia/Sepia), fault=deimatic blanch with dark-edged eye spots + red edge, '
    + 'unknown=neutral grey hatch (no identity hue)',
  maxColorsWorking: 48,
  fps: 4,
};

// ---- palette (neutrals + alarm colours are fixed; identity tones come from session.hue_deg) -------------
const GROUND = [232, 228, 220];   // leucophore
const BLANCH = [251, 249, 245];   // deimatic blanch
const INK = '#1b1a19';
const PLATE_PALE = '#f3efe8';
const AMBER = [255, 194, 71];
const AMBER_HEX = '#ffc247';
const ALARM_DARK = [27, 26, 25];  // INPUT plate
const FAULT_PLATE = '#8f1d17';
const FAULT_RED = [200, 40, 30];
const HATCH_A = [214, 214, 214], HATCH_B = [128, 128, 128];

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

export function authoredPairs() {
  return [
    { fg: INK, bg: PLATE_PALE, where: 'name label / unknown ? (pale plate)' },
    { fg: AMBER_HEX, bg: '#1b1a19', where: 'needs-you alarm text INPUT (dark plate)' },
    { fg: '#ffffff', bg: FAULT_PLATE, where: 'fault alarm text ERROR (red plate)' },
  ];
}

// ---- colour ------------------------------------------------------------------------------------------
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  for (let c = C; ; c -= 0.004) {
    const a = Math.max(c, 0) * Math.cos(h), b = Math.max(c, 0) * Math.sin(h);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
    if (c <= 0 || lin.every((v) => v >= -0.0005 && v <= 1.0005)) {
      return lin.map((v) => {
        const x = Math.min(1, Math.max(0, v));
        return Math.round(255 * (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055));
      });
    }
  }
}

// identity tones: [light, mid, dark] — same hue, three discrete lightness steps (survives 256 banding)
function tones(session) {
  const h = session && session.hue_deg;
  if (h == null) return [[196, 196, 196], [150, 150, 150], [96, 96, 96]]; // never reached by identity states
  return [oklch(0.80, 0.075, h), oklch(0.60, 0.13, h), oklch(0.36, 0.115, h)];
}
const levelOf = (e) => (e < 0.3 ? -1 : e < 0.55 ? 0 : e < 0.8 ? 1 : 2);

// ---- deterministic noise -----------------------------------------------------------------------------
function hash(x, y, s = 0) {
  let n = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(s | 0, 2147483647);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x, y, s) {
  const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash(x0, y0, s), b = hash(x0 + 1, y0, s), c = hash(x0, y0 + 1, s), d = hash(x0 + 1, y0 + 1, s);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
const seedOf = (session) => {
  const id = (session && session.lineage_id) || 'unbound';
  let n = 7;
  for (let i = 0; i < id.length; i++) n = (Math.imul(n, 31) + id.charCodeAt(i)) | 0;
  return n;
};

// ---- expansion fields (one per state) ------------------------------------------------------------------
function field(state, nx, ny, seed, tq) {
  if (state === 'idle') {              // stipple: sparse, small, static
    return (cx, cy) => { const r = hash(cx, cy, seed); return r < 0.17 ? 0.55 + 0.45 * hash(cx, cy, seed + 1) : 0; };
  }
  if (state === 'working') {           // passing cloud: a dense band drifting right, soft sparse edges
    const bw = Math.max(3, nx * 0.13), speed = Math.max(1.5, nx / 24), span = nx + 4 * bw;
    const u0 = (nx * 0.34 + (seed & 7) + tq * speed) % span - bw;
    return (cx, cy) => {
      const d = (cx - u0 - (cy - ny / 2) * 0.35) / bw;
      const dens = Math.exp(-d * d * 1.2);
      return hash(cx, cy, seed) < dens * 1.15 ? 0.45 + 0.55 * dens : 0;
    };
  }
  if (state === 'review') {            // mottle: irregular contiguous light/dark patches
    const sx = Math.max(4, nx / 16), sy = Math.max(2, ny / 2.2);
    return (cx, cy) => {
      const n = 0.65 * vnoise(cx / sx, cy / sy, seed) + 0.35 * vnoise(cx / (sx * 0.5) + 9, cy / (sy * 0.5), seed + 3);
      return n < 0.42 ? 0 : n < 0.56 ? 0.45 : n < 0.68 ? 0.7 : 0.95;
    };
  }
  return () => 0;
}

// ---- helpers over the pixel buffer ---------------------------------------------------------------------
function makeBuf(w, h) { return { w, h, px: new Uint8ClampedArray(w * h * 4) }; }
function put(b, x, y, c) {
  if (x < 0 || y < 0 || x >= b.w || y >= b.h) return;
  const i = (y * b.w + x) * 4;
  b.px[i] = c[0]; b.px[i + 1] = c[1]; b.px[i + 2] = c[2]; b.px[i + 3] = 255;
}
function rect(b, x0, y0, x1, y1, c) { for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) put(b, x, y, c); }

// Sac field → pixels. p = sac pitch in px (XL: discs; M/S: one pixel = one sac).
function paintSacs(b, f, tn, ground, p) {
  for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
    const cx = Math.floor(x / p), cy = Math.floor(y / p), e = f(cx, cy), lv = levelOf(e);
    if (lv < 0) { put(b, x, y, ground); continue; }
    if (p === 1) { put(b, x, y, tn[lv]); continue; }
    const r = (0.35 + 0.65 * e) * p / 2, dx = x - (cx * p + p / 2 - 0.5), dy = y - (cy * p + p / 2 - 0.5);
    put(b, x, y, dx * dx + dy * dy <= r * r ? tn[lv] : ground);
  }
}

function eye(b, cx, cy, rx, ry, ring, core, cf = 0.5) {
  for (let y = Math.floor(cy - ry - 1); y <= Math.ceil(cy + ry + 1); y++) for (let x = Math.floor(cx - rx - 1); x <= Math.ceil(cx + rx + 1); x++) {
    const d = Math.hypot((x - cx) / rx, (y - cy) / ry);
    if (d <= cf) put(b, x, y, core); else if (d <= 1) put(b, x, y, ring);
  }
}

// ---- text + plates ----------------------------------------------------------------------------------------
function layout(scale, w, h, state, session, degraded) {
  const text = [], plates = [];
  const name = degraded ? 'unbound' : session.name;
  const alarm = session.alarm_text;
  const tag = state === 'unknown' ? '?' : (state === 'needs-you' || state === 'fault') ? alarm : null;
  const tagStyle = state === 'needs-you' ? { fg: AMBER_HEX, bg: '#1b1a19' }
    : state === 'fault' ? { fg: '#ffffff', bg: FAULT_PLATE } : { fg: INK, bg: PLATE_PALE };
  const nameStyle = { fg: INK, bg: PLATE_PALE };
  if (scale === 'XL') {
    const cw = 9, th = 24;
    text.push({ x: 14, y: 14, str: name, ...nameStyle });
    plates.push({ x0: 8, y0: 8, x1: 20 + name.length * cw, y1: 8 + th + 6, c: hex(nameStyle.bg) });
    if (tag) {
      const ty = h - 14 - th;
      text.push({ x: 14, y: ty, str: tag, ...tagStyle });
      plates.push({ x0: 8, y0: ty - 6, x1: 20 + tag.length * cw, y1: ty + th + 6, c: hex(tagStyle.bg) });
    }
    return { text, plates, free: Math.max(20 + name.length * cw, tag ? 20 + tag.length * cw : 0) + 12 };
  }
  const nm = name.slice(0, Math.max(1, Math.min(10, w - 4)));
  const rowH = h >= 4 ? h / 2 : h;
  let end = 0;
  const add = (str, col, row, st) => {
    text.push({ x: col, y: row, str, ...st });
    const y0 = Math.floor(row * rowH), y1 = Math.min(h, Math.ceil((row + 1) * rowH));
    plates.push({ x0: col - 1, y0, x1: col + str.length + 1, y1, c: hex(st.bg) });
    end = Math.max(end, col + str.length + 1);
  };
  if (h >= 4) {                       // two rows: tag on row 0, name on row 1
    if (tag && 1 + tag.length + 1 <= w) add(tag, 1, 0, tagStyle);
    add(nm, 1, 1, nameStyle);
  } else {                            // one pixel-row pair: name then tag on the same cell row
    add(nm, 1, 0, nameStyle);
    if (tag && end + 1 + tag.length + 1 <= w) add(tag, end + 1, 0, tagStyle);
    else if (tag && scale === 'S') { text.length = 0; plates.length = 0; end = 0; add(tag, 1, 0, tagStyle); } // alarm outranks name when the pill is tight
  }
  return { text, plates, free: end + 1 };
}

// ---- paint ---------------------------------------------------------------------------------------------------
export function paint({ scale, w, h, state, session, t = 0, opts = {} }) {
  const degraded = session.hue_deg == null;
  const b = makeBuf(w, h);
  const seed = seedOf(session);
  const tn = tones(session);
  const p = scale === 'XL' ? Math.max(4, Math.round(w / 40)) : 1;
  const nx = Math.ceil(w / p), ny = Math.ceil(h / p);
  const tq = state === 'working' && !opts.reducedMotion ? Math.floor(t * 4) / 4 : 0;
  const lay = layout(scale, w, h, state, session, degraded);
  const sw = scale === 'XL' ? Math.max(3, Math.round(w / 40)) : (w >= 60 ? 2 : 1);
  const eyeR = scale === 'XL' ? Math.round(h / 7) : Math.max(1, h / 2);
  const eyeRx = scale === 'XL' ? eyeR : (h >= 4 ? eyeR * 1.4 : 2.6);
  const cyE = scale === 'XL' ? h / 2 : h / 2 - 0.5;
  const dark = tn[2];

  if (state === 'idle' || state === 'working' || state === 'review') {
    paintSacs(b, field(state, nx, ny, seed, tq), tn, GROUND, p);
  } else if (state === 'needs-you') {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) put(b, x, y, Math.floor(x / sw) % 2 === 0 ? dark : GROUND);
    const gap = eyeRx * 2 + (scale === 'XL' ? 40 : 3), room = w - lay.free;
    const eyes = room >= gap + eyeRx * 2 + 2 ? [lay.free + room * 0.30, lay.free + room * 0.30 + gap]
      : room >= eyeRx * 2 + 2 ? [w - eyeRx - 1.5] : [];
    // each eye sits on a pale halo so the ring reads against the stripes
    for (const ex of eyes) {
      eye(b, ex, cyE, eyeRx + (scale === 'XL' ? 8 : 1), eyeR + (scale === 'XL' ? 8 : 0), GROUND, GROUND);
      eye(b, ex, cyE, eyeRx, eyeR, ALARM_DARK, AMBER);
    }
  } else if (state === 'fault') {
    rect(b, 0, 0, w, h, BLANCH);
    const bw = scale === 'XL' ? 8 : 2;
    rect(b, w - bw, 0, w, h, FAULT_RED);
    if (scale === 'XL') { rect(b, 0, 0, w, bw, FAULT_RED); rect(b, 0, h - bw, w, h, FAULT_RED); rect(b, 0, 0, bw, h, FAULT_RED); }
    const room = w - lay.free - bw, ex = Math.max(eyeRx * 2.2, scale === 'XL' ? w * 0.18 : eyeRx * 2.2);
    const eyes = room >= ex * 2 + 4 ? [lay.free + room * 0.25, lay.free + room * 0.25 + ex * 1.2 + eyeRx]
      : room >= eyeRx * 2 + 2 ? [w - bw - eyeRx - 1.5] : [];
    const fr = scale === 'XL' ? eyeR * 1.15 : eyeR;
    for (const x of eyes) { eye(b, x, cyE, scale === 'XL' ? fr : eyeRx, fr, dark, BLANCH, h >= 4 || scale === 'XL' ? 0.5 : 0.62); }
  } else {                            // unknown: neutral diagonal hatch, no identity hue
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const q = scale === 'XL' ? Math.floor((x + y) / Math.max(3, Math.round(w / 60))) : x + (y >= 0 ? y * 2 : 0);
      put(b, x, y, (q % 4 + 4) % 4 < 2 ? HATCH_B : HATCH_A);
    }
  }
  for (const pl of lay.plates) rect(b, Math.max(0, pl.x0), Math.max(0, pl.y0), Math.min(w, pl.x1), Math.min(h, pl.y1), pl.c);
  return { pixels: b.px, text: lay.text };
}
