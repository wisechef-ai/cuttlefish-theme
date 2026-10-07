// Direction B — "Metasepia flamboyant" (round 2).
// Pure ESM: no imports, no timers, no I/O, no Math.random / Date.now. Seed = session.lineage_id, clock = t.
//
// The skin is a saturated identity-hue dermis (the ground owns most of every tile) that is LAYERED like the animal's:
// a relief (folds + papillae, lit from the upper left), leucophore pale patches, and chromatophore sacs in three size
// classes whose expansion follows a domain-warped, multi-scale field. Every state is an expansion/retraction pattern
// of those sacs (plus the alarm pigments on the two alarm states); there are no rectangles, straight stripes or grids.
// Colour per pixel = one scalar pigment value v on a per-session tone ramp (leucophore light -> vivid identity
// ground -> deep identity -> tinted ink); shading moves v too, so a working frame stays <= 40 colours.

export const meta = {
  id: 'b-disruptive',
  name: 'Metasepia flamboyant',
  biology:
    'Metasepia pfefferi / Sepia officinalis dermis read boldly: idle = chromatophore stipple in three sac sizes over ' +
    'a lit, papillate relief; working = passing cloud (a soft dark wave of expanded sacs drifting across); review = ' +
    'two-scale mottle (leucophore blotches + dark patches); needs-you = wavy tapering zebra bands + amber soft-ringed ' +
    'eyespots; fault = deimatic blanch, dark-ringed spots, red flush at the margins; unknown = neutral wavy hatch',
  maxColorsWorking: 48,
  fps: 4,
};

// ================================================================ colour
const lin2s = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);

function labToLinear(L, a, b) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}
const inGamut = (rgb) => rgb.every((v) => v >= -0.0005 && v <= 1.0005);
const toSrgb8 = (rgb) => rgb.map((v) => Math.round(255 * lin2s(Math.min(1, Math.max(0, v)))));

/** Largest in-gamut chroma at (L, hue), by bisection. */
function maxChroma(L, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  let lo = 0, hi = 0.4;
  for (let k = 0; k < 18; k++) {
    const mid = (lo + hi) / 2;
    if (inGamut(labToLinear(L, mid * Math.cos(h), mid * Math.sin(h)))) lo = mid; else hi = mid;
  }
  return lo;
}
/** OKLCh -> sRGB8, chroma reduced (hue and lightness kept) until it is in gamut. */
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const c = Math.min(C, maxChroma(L, hDeg));
  return toSrgb8(labToLinear(L, c * Math.cos(h), c * Math.sin(h)));
}
const hex = (c) => '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
const mixC = (a, b, f) => [0, 1, 2].map((j) => Math.round(a[j] + (b[j] - a[j]) * f));
const WHITE = [255, 255, 255], BLACK = [0, 0, 0];
/** Light a colour by the relief: s > 0 faces the light. */
const shadeC = (c, s) => (s >= 0 ? mixC(c, WHITE, 0.32 * Math.min(1, s)) : mixC(c, BLACK, 0.42 * Math.min(1, -s)));

/** The vivid identity ground: the lightness (in a band) where this hue holds the most chroma, capped. */
function groundOf(hue) {
  let best = { L: 0.6, C: 0 };
  for (let L = 0.5; L <= 0.761; L += 0.02) {
    const C = Math.min(0.2, maxChroma(L, hue));
    if (C > best.C + 0.004) best = { L, C };
  }
  return best;
}

/** n levels interpolated in OKLCh between stops [[v, L, C], ...] at a fixed hue. */
function rampFrom(stops, hue, n) {
  const r = [];
  for (let i = 0; i < n; i++) {
    const v = i / (n - 1);
    let k = 0;
    while (k < stops.length - 2 && v > stops[k + 1][0]) k++;
    const [v0, L0, C0] = stops[k], [v1, L1, C1] = stops[k + 1];
    const f = (v - v0) / (v1 - v0);
    r.push(oklch(L0 + (L1 - L0) * f, C0 + (C1 - C0) * f, hue));
  }
  return r;
}
const RAMPS = new Map();
/** Identity tone ramp: 0 leucophore light · 0.34 vivid identity ground · 0.68 deep identity · 1 tinted ink. */
function rampOf(hue, n) {
  const key = hue + ':' + n;
  if (!RAMPS.has(key)) {
    const g = groundOf(hue);
    RAMPS.set(key, rampFrom([[0, 0.93, 0.045], [0.34, g.L, g.C], [0.68, 0.4, 0.15], [1, 0.17, 0.035]], hue, n));
  }
  return RAMPS.get(key);
}
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
const pick = (ramp, v) => ramp[Math.round(clamp01(v) * (ramp.length - 1))];

// Alarm pigments (never identity; only on needs-you / fault). Neutrals for unknown / blanch.
const AMBER = oklch(0.84, 0.17, 80);
const AMBER_DEEP = oklch(0.62, 0.15, 60);
const RED = oklch(0.55, 0.21, 27);
const RED_DEEP = oklch(0.38, 0.14, 25);
const INK = oklch(0.17, 0.004, 260);
const GREYS = rampFrom([[0, 0.88, 0], [1, 0.26, 0]], 0, 48);
const BLANCH = rampFrom([[0, 0.97, 0.01], [1, 0.5, 0.012]], 85, 48);

const PLATE = {
  alarmInput: { bg: '#ffb000', fg: '#1a1200' },
  alarmError: { bg: '#b3001b', fg: '#ffffff' },
  unknown: { bg: '#d8d8d8', fg: '#111111' },
  nameNeutral: { bg: '#2a2a2a', fg: '#ffffff' },
};
const namePlate = (hue) => hex(oklch(0.28, 0.07, hue));

// ================================================================ deterministic noise
function seedOf(session) {
  const s = String((session && (session.lineage_id || session.name)) || 'cuttlefish');
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
function h2(x, y, s) {
  let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(s | 0, 2246822519)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
const sstep = (t) => t * t * (3 - 2 * t);
const smooth = (e0, e1, x) => sstep(clamp01((x - e0) / (e1 - e0)));

function vnoise(x, y, s) {
  const ix = Math.floor(x), iy = Math.floor(y);
  const fx = sstep(x - ix), fy = sstep(y - iy);
  const a = h2(ix, iy, s), b = h2(ix + 1, iy, s), c = h2(ix, iy + 1, s), d = h2(ix + 1, iy + 1, s);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}
function fbm(x, y, s, oct = 3) {
  let v = 0, amp = 0.5, tot = 0;
  for (let o = 0; o < oct; o++) {
    v += amp * vnoise(x, y, s + o * 101);
    tot += amp;
    x = x * 2.03 + 17.1; y = y * 2.03 - 9.7; amp *= 0.5;
  }
  return v / tot;
}
/** Domain-warped field: fbm sampled at a point displaced by two other fbm fields (k = warp strength). */
function warped(x, y, s, k) {
  const qx = fbm(x + 3.1, y - 1.7, s + 7), qy = fbm(x - 5.3, y + 2.9, s + 13);
  return fbm(x + k * (qx - 0.5), y + k * (qy - 0.5), s + 29);
}

/**
 * One size class of round cells (chromatophore sacs, papillae): one jittered cell per lattice square, with hashed
 * presence, radius and position, so nothing tiles. profile 0 = soft-edged disc (coverage), 1 = dome (height).
 */
function cells(x, y, cell, s, density, expand, soft, rmin, rspan, profile) {
  const ix = Math.floor(x / cell), iy = Math.floor(y / cell);
  let best = 0;
  for (let dy = -1; dy <= 1; dy++)
    for (let dx = -1; dx <= 1; dx++) {
      const cx = ix + dx, cy = iy + dy;
      if (h2(cx, cy, s + 2) > density) continue;
      const ex = x - (cx + 0.1 + 0.8 * h2(cx, cy, s)) * cell;
      const ey = y - (cy + 0.1 + 0.8 * h2(cx, cy, s + 1)) * cell;
      const r = cell * (rmin + rspan * h2(cx, cy, s + 3)) * expand;
      const lim = profile ? r : r + soft;
      const d2 = ex * ex + ey * ey;
      if (d2 >= lim * lim) continue;
      const d = Math.sqrt(d2);
      const c = profile ? (1 - d / r) * (1 - d / r) : clamp01((r - d) / soft + 0.5);
      if (c > best) best = c;
    }
  return best;
}

// ================================================================ geometry + shared fields
/**
 * World coordinates: logical px are ~square on every host except the TUI bg rung (one pixel per tall cell), so
 * M/S sample the same world as the half rung there (a 2-row bg mantle = the 4-row half mantle, every other row).
 * XL is the field pane at ~1/4 CSS resolution; `u` = paint px per design unit, so features keep their on-screen
 * size whatever the pane's size. F = feature sizes in world px.
 */
function geometry(scale, w, h) {
  if (scale === 'XL') {
    const u = Math.max(0.5, Math.sqrt((w * h) / 51000));
    return { sy: 1, wh: h, xl: true, shade: 0.2,
      F: { fine: 2.1 * u, med: 5.4 * u, big: 12 * u, macro: 48 * u, soft: 1.1 * u, step: Math.max(1, Math.round(2 * u)) } };
  }
  const sy = scale === 'M' ? Math.max(1, 4 / h) : h <= 1 ? 2 : 1;
  return { sy, wh: h * sy, xl: false, shade: 0.06, F: { fine: 1.15, med: 3.4, big: 7.5, macro: 26, soft: 0.45, step: 1 } };
}

const MEMO = new Map();
/** Small LRU memo for pure, expensive per-(session, size) layers. Keys carry every input, so it is invisible. */
function memo(key, make) {
  let v = MEMO.get(key);
  if (v) { MEMO.delete(key); MEMO.set(key, v); return v; }
  v = make();
  MEMO.set(key, v);
  if (MEMO.size > 64) MEMO.delete(MEMO.keys().next().value);
  return v;
}

/** Sample a smooth field on a coarse lattice (every `step` px) and bilinearly fill the w*h grid. */
function coarse(w, h, sy, step, fn) {
  const cw = Math.ceil(w / step) + 2, ch = Math.ceil(h / step) + 2;
  const c = new Float32Array(cw * ch);
  for (let j = 0; j < ch; j++) for (let i = 0; i < cw; i++) c[j * cw + i] = fn(i * step + 0.5, (j * step + 0.5) * sy);
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const fy = y / step, j = Math.floor(fy), ty = fy - j;
    for (let x = 0; x < w; x++) {
      const fx = x / step, i = Math.floor(fx), tx = fx - i;
      const a = c[j * cw + i], b = c[j * cw + i + 1], d = c[(j + 1) * cw + i], e = c[(j + 1) * cw + i + 1];
      out[y * w + x] = a + (b - a) * tx + (d - a) * ty + (a - b - d + e) * tx * ty;
    }
  }
  return out;
}

/**
 * Per-(session, size) dermis fields shared by every state: macro tone, sac-expansion field E, the sac-flow warp,
 * and the lit relief S (folds + papillae + granules, light from the upper left), in [-1, 1].
 */
function fieldsOf(G, seed, w, h) {
  return memo(`f|${seed}|${w}x${h}|${G.xl}|${G.sy}`, () => {
    const F = G.F, st = F.step;
    const macro = coarse(w, h, G.sy, st, (x, y) => warped(x / F.macro, y / F.macro, seed + 61, 2.0));
    const E = coarse(w, h, G.sy, st, (x, y) => warped(x / (0.55 * F.macro), y / (0.55 * F.macro), seed + 71, 1.8));
    const fold = coarse(w, h, G.sy, st, (x, y) => warped(x / (0.5 * F.macro), y / (0.3 * F.macro), seed + 91, 2.4));
    const qx = coarse(w, h, G.sy, st, (x, y) => fbm(x / (2.6 * F.med), y / (2.6 * F.med), seed + 41) - 0.5);
    const qy = coarse(w, h, G.sy, st, (x, y) => fbm(x / (2.6 * F.med) + 7, y / (2.6 * F.med) - 3, seed + 43) - 0.5);
    const H = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const i = y * w + x, wx = x + 0.5 + 0.9 * F.med * qx[i], wy = (y + 0.5) * G.sy + 0.9 * F.med * qy[i];
        const pap = cells(wx + 3.7, wy - 8.1, F.med * 1.35, seed + 5000, 0.75, 1, 0, 0.3, 0.25, 1);
        const gran = G.xl ? cells(wx, wy, F.fine * 0.9, seed + 5100, 0.8, 1, 0, 0.35, 0.2, 1) : 0;
        H[i] = 2.2 * fold[i] + 0.55 * pap + 0.22 * gran;
      }
    const S = new Float32Array(w * h);
    const at = (x, y) => H[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];
    const gain = G.xl ? 2.2 : 1.6;
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) S[y * w + x] = Math.max(-1, Math.min(1, (at(x - 1, y - 1) - at(x + 1, y + 1)) * gain));
    return { macro, E, qx, qy, S };
  });
}

// ================================================================ pigment (one value v per pixel)
/**
 * The resting dermis pigment at pixel i (world x, y): vivid identity ground with macro drift, pale leucophore
 * patches where sacs are retracted, and three sac classes whose expansion follows E. `boost` (0..1, the passing
 * cloud) expands every sac and darkens the ground; `band` (0..1, the zebra) does the same along the bands.
 */
function dermisV(G, seed, f, i, x, y, boost, review) {
  const F = G.F;
  const wx = x + 0.9 * F.med * f.qx[i], wy = y + 0.9 * F.med * f.qy[i];
  const E = f.E[i], m = f.macro[i];
  let v = 0.34 + 0.3 * (m - 0.5);
  const pale = smooth(0.55, 0.7, m) * (1 - smooth(0.35, 0.6, E));
  v -= 0.24 * pale * (1 - boost);
  const ex = (review ? 0.75 + 0.45 * E : 0.5 + 0.8 * smooth(0.3, 0.72, E)) * (1 + 1.1 * boost);
  const c2 = cells(wx + 11.3, wy - 4.1, F.med, seed + 2000, 0.55, ex, F.soft * (G.xl ? 1.6 : 1), 0.16, 0.24, 0);
  const c3 = cells(wx - 23.7, wy + 9.9, F.big, seed + 3000, 0.42, ex * smooth(0.35, 0.75, E) * 1.1, F.soft * (G.xl ? 2.4 : 1.4), 0.14, 0.22, 0);
  if (G.xl) v += 0.12 * cells(wx, wy, F.fine, seed + 1000, 0.65, ex, F.soft, 0.18, 0.2, 0);
  v += 0.24 * boost;
  v += (Math.max(v, 0.7) - v) * c2; // medium sacs: deep identity
  v += (Math.max(v, 0.95) - v) * c3; // large sacs: near ink
  return v;
}

function skinState(state, hue, w, h, G, seed, t, opts) {
  const F = G.F;
  const f = fieldsOf(G, seed, w, h);
  const sh = G.shade;
  if (state === 'idle') {
    const ramp = rampOf(hue, 64);
    return (x, y, i) => pick(ramp, dermisV(G, seed, f, i, x, y, 0, false) - sh * f.S[i]);
  }
  if (state === 'review') {
    // Mottle: irregular leucophore-white blotches and dark patches at two scales over the dermis.
    const ramp = rampOf(hue, 64);
    const A = coarse(w, h, G.sy, F.step, (x, y) => warped(x / (0.42 * F.macro), y / (0.42 * F.macro), seed + 131, 2.4));
    return (x, y, i) => {
      const a = A[i];
      const b = warped(x / (0.16 * F.macro), y / (0.16 * F.macro), seed + 137, 1.6);
      const light = smooth(0.55, 0.64, a) * (0.6 + 0.4 * smooth(0.4, 0.6, b));
      const dark = smooth(0.42, 0.34, a) * smooth(0.45, 0.58, b);
      let v = dermisV(G, seed, f, i, x, y, 0, true);
      v = v * (1 - light) + 0.06 * light;
      v = Math.max(v, 0.34 + 0.5 * dark);
      return pick(ramp, v - sh * f.S[i]);
    };
  }
  // working — passing cloud: a soft, ragged dark wave of expanded sacs drifting right at <= 4 fps.
  const ramp = rampOf(hue, 40);
  const tq = opts.reducedMotion ? 0 : Math.floor((t || 0) * 4) / 4;
  const tiny = w <= 8;
  const span = tiny ? w : w * (G.xl ? 1.6 : 1.35);
  const speed = tiny ? w : G.xl ? 2.3 * F.med : 5; // world px / s; the 4-px swatch moves one px per frame
  const width = tiny ? 1.3 : (G.xl ? 0.3 : 0.2) * w;
  const x0 = (tiny ? 0.5 : 0.45 * w) + speed * tq;
  const L = memo(`w|${seed}|${w}x${h}|${G.xl}|${G.sy}`, () => {
    const rest = new Float32Array(w * h), full = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        rest[i] = dermisV(G, seed, f, i, x + 0.5, (y + 0.5) * G.sy, 0, false);
        full[i] = dermisV(G, seed, f, i, x + 0.5, (y + 0.5) * G.sy, 1, false);
      }
    return { rest, full };
  });
  return (x, y, i) => {
    const rag = (fbm(x / (1.6 * F.med), y / (1.6 * F.med) + tq * 0.5, seed + 97) - 0.5) * (tiny ? 0.6 : 0.8) * width;
    const slant = G.xl ? (y - G.wh / 2) * 0.3 : 0;
    let d = x + rag - slant - x0;
    d = (((d % span) + span * 1.5) % span) - span / 2; // wrap: the wave re-enters from the left
    const cl = smooth(width, width * 0.2, Math.abs(d));
    return pick(ramp, L.rest[i] + (L.full[i] - L.rest[i]) * cl - sh * f.S[i]);
  };
}

// ================================================================ alarm displays
/** Concentric soft rings: `stops` = [[d, colour], ...] ascending; colours blend across `aa` around each edge. */
function rings(d, stops, aa) {
  let c = stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    const e = stops[i][0];
    const f = smooth(e - aa, e + aa, d);
    if (f <= 0) break;
    c = f >= 1 ? stops[i][1] : mixC(c, stops[i][1], f);
  }
  return c;
}

/** Eyespot centres (world coords): spread along the body, clear of the text at the left, slightly irregular. */
function eyespots(w, G, seed, tiny) {
  if (tiny) return [{ x: w - 1.5, y: G.wh / 2, rx: 1.35, ry: 1.25, pupil: false }];
  const out = [];
  if (G.xl) {
    const u = G.F.med / 5.4, n = 3;
    for (let i = 0; i < n; i++) {
      const fx = 0.24 + 0.52 * ((i + 0.5) / n) + 0.1 * (h2(i, 1, seed + 301) - 0.5);
      const fy = 0.22 + 0.56 * h2(i, 2, seed + 301);
      const r = (17 + 9 * h2(i, 3, seed + 301)) * u;
      out.push({ x: fx * w, y: fy * G.wh, rx: r * 1.1, ry: r, pupil: true });
    }
    return out;
  }
  const n = Math.max(1, Math.min(4, Math.floor((w - 12) / 26)));
  const x0 = w <= 30 ? w * 0.72 : Math.max(24, w * 0.3);
  const x1 = w - 5;
  for (let i = 0; i < n; i++) {
    const f = n === 1 ? 0.5 : i / (n - 1);
    out.push({ x: x0 + (x1 - x0) * f + 2 * (h2(i, 5, seed + 307) - 0.5), y: G.wh / 2, rx: 3.1, ry: 2.25, pupil: G.wh >= 4 });
  }
  return out;
}

function zebra(hue, w, h, G, seed) {
  // Sepia "intense zebra": wavy, tapering bands of fully expanded sacs across the body; amber eyespots on top.
  const F = G.F;
  const f = fieldsOf(G, seed, w, h);
  const ramp = rampOf(hue, 64);
  const tiny = w <= 8;
  const per = G.xl ? 2.6 * F.med : tiny ? 2.6 : 5.2;
  const eyes = eyespots(w, G, seed, tiny);
  const aa = G.xl ? 0.05 : 0.1;
  const bend = coarse(w, h, G.sy, F.step, (x, y) => warped(x / (0.38 * F.macro), y / (0.38 * F.macro), seed + 171, 2.0));
  const duty = coarse(w, h, G.sy, F.step, (x, y) => fbm(x / (0.45 * F.macro), y / (0.2 * F.macro) + 4, seed + 177));
  const band = (x, y, i) => {
    const ph = (x + (G.xl ? (y - G.wh / 2) * 0.22 : 0)) / per + 1.4 * (bend[i] - 0.5) * 2;
    const taper = 0.3 + 0.24 * duty[i]; // band width varies along the body: bands taper and swell
    const fr = ph - Math.floor(ph);
    return smooth(taper + 0.08, taper - 0.08, fr);
  };
  const skinAt = (x, y, i) => {
    const b = band(x, y, i);
    const v = dermisV(G, seed, f, i, x, y, 0.15 + 0.85 * b, false) * (G.xl ? 1 : 0.4) + (G.xl ? 0.12 * b : 0.2 + 0.62 * b);
    return pick(ramp, v - G.shade * f.S[i]);
  };
  return (x, y, i) => {
    for (const e of eyes) {
      const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
      if (d < 1.3) {
        const st = e.pupil ? [[0, INK], [0.34, AMBER], [0.7, AMBER_DEEP], [0.95, INK]] : [[0, AMBER], [0.72, AMBER_DEEP], [0.96, INK]];
        const c = G.xl ? shadeC(rings(d, st, aa), 0.8 * f.S[i]) : rings(d, st, aa);
        return d < 1.2 ? c : mixC(c, skinAt(x, y, i), smooth(1.2, 1.3, d));
      }
    }
    return skinAt(x, y, i);
  };
}

// ================================================================ chrome scales (M / S): the same grammar, posterised
/**
 * At M and S a strip is 1-4 logical px tall, so the dermis is drawn as a bold graphic: four flat identity tones
 * (light, ground, deep, ink), crisp shapes, hashed rhythm (sizes and gaps vary, nothing tiles). Same seed, same
 * state grammar as the XL field; structure, not shading, so it survives the bg rung, the 256 rung and CVD sims.
 */
function graphic(state, hue, w, h, G, seed, t, opts) {
  const tiny = w <= 8;
  if (hue === null || state === 'unknown') {
    // neutral wavy hatch, two greys
    const g0 = GREYS[30], g1 = GREYS[12];
    return (x, y) => {
      const ph = (x + 1.15 * y) / 4.6 + 0.7 * (warped(x / 13, y / 13, seed + 5, 2.0) - 0.5) * 2;
      return ph - Math.floor(ph) < 0.5 ? g0 : g1;
    };
  }
  const ramp = rampOf(hue, 64);
  const T = { light: pick(ramp, 0.1), ground: pick(ramp, 0.34), mid: pick(ramp, 0.52), deep: pick(ramp, 0.72), ink: pick(ramp, 0.97) };
  // stipple: one spot per hashed slot along the strip; three sac sizes at varied heights
  const SL = tiny ? 2 : 5.3;
  const spot = (x, y, grow) => {
    const k0 = Math.floor(x / SL);
    for (let k = k0 - 1; k <= k0 + 1; k++) {
      const r0 = h2(k, 0, seed + 11);
      if (r0 > (tiny ? 0.7 : 0.82)) continue; // some slots stay empty: irregular rhythm
      const cls = tiny ? 0 : r0 < 0.3 ? 2 : r0 < 0.58 ? 1 : 0;
      const cx = (k + 0.2 + 0.6 * h2(k, 1, seed + 11)) * SL;
      const cy = cls === 2 ? 2 : 0.8 + 2.4 * h2(k, 2, seed + 11);
      const rx = ([0.62, 1.15, 1.7][cls] + (tiny ? 0 : 0.25 * h2(k, 3, seed + 11))) * grow;
      const ry = [0.62, 1.05, 1.55][cls] * grow;
      const d = Math.hypot((x - cx) / rx, (y - cy) / ry);
      if (d < 1) return cls === 0 ? T.deep : d < 0.55 || cls === 2 ? T.ink : T.deep;
    }
    return null;
  };
  if (state === 'idle') return (x, y) => spot(x, y, 1) || T.ground;
  if (state === 'working') {
    const tq = opts.reducedMotion ? 0 : Math.floor((t || 0) * 4) / 4;
    const span = tiny ? w : w * 1.35;
    const width = tiny ? 1.2 : 0.11 * w + 3;
    const x0 = (tiny ? 0.5 : 0.45 * w) + (tiny ? w : 5) * tq;
    return (x, y) => {
      const rag = tiny ? 0 : 2.2 * (fbm(x / 6, y / 3 + 3.1, seed + 97) - 0.5) * 2;
      let d = x + rag - x0;
      d = (((d % span) + span * 1.5) % span) - span / 2;
      const a = Math.abs(d);
      const core = a < width * 0.55, fringe = a < width;
      const s = spot(x, y, fringe ? 1.35 : 1);
      if (core) return s ? T.ink : T.deep;
      if (fringe) return s ? T.ink : T.mid;
      return s || T.ground;
    };
  }
  if (state === 'review') {
    // two-scale mottle: irregular pale and dark patches with wavy edges
    return (x, y) => {
      const a = warped(x / 7.5, y / 6, seed + 131, 2.2);
      const b = vnoise(x / 2.6, y / 2.2, seed + 137);
      if (a > 0.58 || (a > 0.5 && b > 0.72)) return T.light;
      if (a < 0.38 || (a < 0.45 && b < 0.25)) return T.deep;
      return spot(x, y, 0.8) ? T.mid : T.ground;
    };
  }
  if (state === 'needs-you') {
    const eyes = eyespots(w, G, seed, tiny);
    return (x, y) => {
      for (const e of eyes) {
        const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
        if (d < 1.05) return e.pupil && d < 0.42 ? INK : AMBER;
      }
      if (tiny) return x < 1.5 ? T.ink : T.ground;
      const ph = x / 5.8 + 0.75 * (warped(x / 15, y / 9, seed + 171, 2.0) - 0.5) * 2 + 0.06 * y;
      const duty = 0.3 + 0.2 * vnoise(x / 11, 0.5, seed + 177); // bands swell and taper along the body
      return ph - Math.floor(ph) < duty ? T.ink : T.ground;
    };
  }
  if (state === 'fault') {
    // deimatic: blanched strip, ink-ringed spots, red flush at both ends (wavy inner edge)
    const eyes = eyespots(w, G, seed, tiny).slice(0, tiny ? 1 : 3);
    const edge = tiny ? 0.8 : Math.max(2.5, w * 0.05);
    return (x, y) => {
      for (const e of eyes) {
        const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
        if (d < 1.05) return d < 0.45 ? RED : INK;
      }
      const dEdge = Math.min(x, w - x) + (tiny ? 0 : 1.6 * (vnoise(y / 1.3, x < w / 2 ? 0.5 : 7.5, seed + 191) - 0.5));
      if (dEdge < edge) return RED;
      return spot(x, y, 0.55) ? BLANCH[10] : BLANCH[0];
    };
  }
  return null;
}

function deimatic(w, h, G, seed) {
  // The body blanches pale (sacs retract to specks), dark-ringed spots flash, the margins flush red.
  const F = G.F;
  const f = fieldsOf(G, seed, w, h);
  const tiny = w <= 8;
  const eyes = eyespots(w, G, seed, tiny).slice(0, tiny ? 1 : G.xl ? 2 : 3);
  const edge = G.xl ? 0.14 * Math.min(w, G.wh) : tiny ? 0.8 : Math.max(2, w * 0.045);
  const aa = G.xl ? 0.05 : 0.1;
  return (x, y, i) => {
    const s = f.S[i] * (G.xl ? 1 : 0.5);
    for (const e of eyes) {
      const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
      if (d < 1.25) return shadeC(rings(d, [[0, BLANCH[6]], [0.45, INK], [0.9, RED_DEEP], [1.12, BLANCH[4]]], aa), s);
    }
    const rag = (fbm(x / (1.2 * F.med), y / (1.2 * F.med), seed + 191) - 0.5) * 2 * (G.xl ? 0.45 * edge : 0.9);
    const dEdge = Math.min(x, w - x, G.xl ? Math.min(y, G.wh - y) : 1e9) + rag;
    const sp = cells(x + 0.9 * F.med * f.qx[i], y + 0.9 * F.med * f.qy[i], F.med * 0.8, seed + 211, 0.55, 0.45, F.soft, 0.16, 0.2, 0);
    const pale = pick(BLANCH, 0.06 + 0.16 * (f.macro[i] - 0.5) + 0.28 * sp - 0.5 * G.shade * f.S[i] * 2);
    const red = shadeC(smooth(edge * 0.35, 0, dEdge) > 0.5 ? RED_DEEP : RED, s);
    return mixC(pale, red, smooth(edge, edge * 0.7, dEdge));
  };
}

function hatch(w, h, G, seed) {
  // Neutral wavy hatch: diagonal threads bent by a warped field (no straight lines), greys only, lit relief.
  const F = G.F;
  const f = fieldsOf(G, seed, w, h);
  const per = G.xl ? 1.4 * F.med : 4.6;
  const wv = coarse(w, h, G.sy, F.step, (x, y) => warped(x / (0.6 * F.macro), y / (0.6 * F.macro), seed + 5, 2.2));
  return (x, y, i) => {
    const ph = (x + y * 1.1) / per + 1.3 * (wv[i] - 0.5) * 2;
    const s = Math.sin(ph * Math.PI * 2);
    const v = 0.25 + 0.5 * smooth(-0.6, 0.6, s) + 0.3 * (f.macro[i] - 0.5) - G.shade * 1.5 * f.S[i];
    return pick(GREYS, v);
  };
}

function patternFn(state, session, w, h, G, t, opts) {
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const seed = seedOf(session);
  if (!G.xl) {
    const g = graphic(state, hue, w, h, G, seed, t, opts);
    if (g) return g;
  }
  if (state === 'fault') return deimatic(w, h, G, seed);
  if (hue === null || !['idle', 'working', 'review', 'needs-you'].includes(state)) return hatch(w, h, G, seed);
  if (state === 'needs-you') return zebra(hue, w, h, G, seed);
  return skinState(state, hue, w, h, G, seed, t, opts);
}

// ================================================================ text (literal, durable)
function labels(state, session) {
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const items = [];
  if (state === 'needs-you' && session.alarm_text) items.push({ str: session.alarm_text, ...PLATE.alarmInput });
  else if (state === 'fault' && session.alarm_text) items.push({ str: session.alarm_text, ...PLATE.alarmError });
  else if (state === 'unknown' || hue === null) items.push({ str: '?', ...PLATE.unknown });
  const nm = session && session.name ? session.name : '';
  if (nm) items.push({ str: nm, bg: hue === null ? PLATE.nameNeutral.bg : namePlate(hue), fg: '#ffffff' });
  return items;
}

function layoutText(scale, state, session, w) {
  if (scale === 'S' && w <= 8) return []; // desktop swatch: no text (D-R2-2); the sidebar row carries the name
  const items = labels(state, session);
  const out = [];
  if (scale === 'XL') {
    // CSS px; one line at the top-left of the pane.
    let x = 14;
    for (const it of items) {
      out.push({ x, y: 12, str: it.str, fg: it.fg, bg: it.bg });
      x += it.str.length * 9 + 14;
    }
    return out;
  }
  // M / S: cell coordinates, row 0, one cell of skin before and between labels; alarm first, the name if it fits.
  let x = 1;
  items.forEach((it, i) => {
    if (i > 0 && x + it.str.length > w - 1) return;
    out.push({ x, y: 0, str: it.str, fg: it.fg, bg: it.bg });
    x += it.str.length + 1;
  });
  return out;
}

// ================================================================ API
export function paint({ scale, w, h, state, session, t, opts }) {
  const px = new Uint8ClampedArray(w * h * 4);
  const G = geometry(scale, w, h);
  const fn = patternFn(state, session, w, h, G, t, opts || {});
  for (let y = 0; y < h; y++) {
    const wy = (y + 0.5) * G.sy;
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const c = fn(x + 0.5, wy, i);
      px[i * 4] = c[0]; px[i * 4 + 1] = c[1]; px[i * 4 + 2] = c[2]; px[i * 4 + 3] = 255;
    }
  }
  return { pixels: px, text: layoutText(scale, state, session, w) };
}

export function authoredPairs() {
  const pairs = [
    { fg: PLATE.alarmInput.fg, bg: PLATE.alarmInput.bg, where: 'M/S/XL alarm text (needs-you)' },
    { fg: PLATE.alarmError.fg, bg: PLATE.alarmError.bg, where: 'M/S/XL alarm text (fault)' },
    { fg: PLATE.unknown.fg, bg: PLATE.unknown.bg, where: 'M/S/XL unknown ?' },
    { fg: PLATE.nameNeutral.fg, bg: PLATE.nameNeutral.bg, where: 'M/S/XL name (unbound)' },
  ];
  for (let hh = 110; hh < 340; hh += 10) pairs.push({ fg: '#ffffff', bg: namePlate(hh), where: `name plate @hue ${hh}` });
  return pairs;
}
