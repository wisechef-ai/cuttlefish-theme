// Direction B — "Metasepia flamboyant" (round 2).
// Pure ESM: no imports, no timers, no I/O, no Math.random / Date.now. Seed = session.lineage_id, clock = t.
//
// One state grammar, drawn at two resolutions:
//  * XL (the field pane, painted at ~1/4 CSS resolution and upscaled smoothly): a saturated identity-hue dermis,
//    layered like the animal's — dense granules, broad soft mottling and pale streaks, a gently lit relief, and
//    chromatophore sacs in three size classes whose expansion follows a domain-warped field. States are expansion
//    patterns of those sacs (a passing dark cloud, mottle, zebra) or the alarm displays (amber eyespots, deimatic
//    blanch). Colour = one pigment value v on a per-session tone ramp, so working frames stay <= 40 colours.
//  * M / S (mantle, chip, pill, swatch: 1-4 px tall): the same grammar posterised into four flat identity tones
//    with crisp, varied, organic shapes; structure, not shading, so it survives the bg rung, 256 colours and CVD.
// No rectangles, straight stripes or regular grids anywhere: every motif is hashed or domain-warped.

export const meta = {
  id: 'b-disruptive',
  name: 'Metasepia flamboyant',
  biology:
    'Metasepia pfefferi / Sepia officinalis skin read boldly: idle = chromatophore stipple (three sac sizes) over a ' +
    'granular, softly mottled dermis; working = passing cloud (a soft dark wave of expanded sacs drifting across); ' +
    'review = two-scale mottle (leucophore blotches + dark patches); needs-you = wavy tapering zebra bands + amber ' +
    'soft-ringed eyespots; fault = deimatic blanch, dark-ringed spots, red flush at the margins; unknown = neutral wavy hatch',
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
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

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
 * presence, radius and position, so nothing tiles. Returns soft-edged disc coverage in [0, 1].
 */
function cells(x, y, cell, s, density, expand, soft, rmin, rspan) {
  const ix = Math.floor(x / cell), iy = Math.floor(y / cell);
  let best = 0;
  for (let dy = -1; dy <= 1; dy++)
    for (let dx = -1; dx <= 1; dx++) {
      const cx = ix + dx, cy = iy + dy;
      if (h2(cx, cy, s + 2) > density) continue;
      const ex = x - (cx + 0.1 + 0.8 * h2(cx, cy, s)) * cell;
      const ey = y - (cy + 0.1 + 0.8 * h2(cx, cy, s + 1)) * cell;
      const r = cell * (rmin + rspan * h2(cx, cy, s + 3)) * expand;
      const lim = r + soft;
      const d2 = ex * ex + ey * ey;
      if (d2 >= lim * lim) continue;
      const c = clamp01((r - Math.sqrt(d2)) / soft + 0.5);
      if (c > best) best = c;
    }
  return best;
}

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

// ================================================================ XL: the field pane
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
function coarse(w, h, step, fn) {
  const cw = Math.ceil(w / step) + 2, ch = Math.ceil(h / step) + 2;
  const c = new Float32Array(cw * ch);
  for (let j = 0; j < ch; j++) for (let i = 0; i < cw; i++) c[j * cw + i] = fn(i * step + 0.5, j * step + 0.5);
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
 * The XL geometry: `u` = paint px per design unit (features keep their on-screen size whatever the pane), and the
 * per-(session, size) fields every state shares: broad mottle, sac-expansion field E, pale streaks, a sac-flow warp
 * (qx, qy), dense granules, and the lit relief S in [-1, 1] (light from the upper left).
 */
function xlField(w, h, seed) {
  return memo(`f|${seed}|${w}x${h}`, () => {
    const u = Math.max(0.5, Math.sqrt((w * h) / 51000));
    const F = { fine: 2.4 * u, med: 5.6 * u, big: 11 * u, macro: 46 * u, soft: 0.8 * u, step: Math.max(1, Math.round(2 * u)) };
    const st = F.step;
    const macro = coarse(w, h, st, (x, y) => warped(x / F.macro, y / F.macro, seed + 61, 2.0));
    const E = coarse(w, h, st, (x, y) => warped(x / (0.55 * F.macro), y / (0.55 * F.macro), seed + 71, 1.8));
    const streak = coarse(w, h, st, (x, y) => warped(x / (0.16 * F.macro), y / (0.42 * F.macro), seed + 83, 2.2));
    const body = coarse(w, h, st, (x, y) => fbm(x / (2.2 * F.macro), y / (2.2 * F.macro), seed + 87, 2));
    const fold = coarse(w, h, st, (x, y) => warped(x / (0.6 * F.macro), y / (0.6 * F.macro), seed + 91, 2.4));
    const qx = coarse(w, h, st, (x, y) => fbm(x / (2.6 * F.med), y / (2.6 * F.med), seed + 41) - 0.5);
    const qy = coarse(w, h, st, (x, y) => fbm(x / (2.6 * F.med) + 7, y / (2.6 * F.med) - 3, seed + 43) - 0.5);
    const gran = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        gran[i] = 0.65 * (vnoise((x + 0.5) / (0.9 * u), (y + 0.5) / (0.9 * u), seed + 7) - 0.5) + 0.35 * (h2(x, y, seed + 9) - 0.5);
      }
    const at = (a, x, y) => a[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];
    const H = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) H[i] = 1.6 * fold[i] + 0.05 * gran[i] + 0.3 * macro[i];
    const S = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) S[y * w + x] = Math.max(-1, Math.min(1, (at(H, x - 1, y - 1) - at(H, x + 1, y + 1)) * 2.4 / u));
    return { u, F, macro, E, streak, body, qx, qy, gran, S };
  });
}

/**
 * The dermis pigment at pixel i (world x, y): identity ground with a broad body gradient, soft mottle, pale streaks,
 * dense granules, and three sac classes whose expansion follows E. `boost` (0..1) expands every sac and darkens
 * the ground (the passing cloud; the zebra bands).
 */
function dermisV(f, seed, i, x, y, boost, review) {
  const F = f.F;
  const E = f.E[i], m = f.macro[i];
  let v = 0.36 + 0.2 * (m - 0.5) + 0.16 * (f.body[i] - 0.5);
  v -= 0.13 * smooth(0.56, 0.72, f.streak[i]) * (1 - boost); // pale leucophore streaks
  v += 0.2 * f.gran[i]; // dense granules
  const wx = x + 0.9 * F.med * f.qx[i], wy = y + 0.9 * F.med * f.qy[i];
  const ex = (review ? 0.8 + 0.4 * E : 0.55 + 0.7 * smooth(0.3, 0.72, E)) * (1 + 0.9 * boost);
  const c1 = cells(wx, wy, F.fine, seed + 1000, 0.8, ex, F.soft, 0.18, 0.18);
  const c2 = cells(wx + 11.3, wy - 4.1, F.med, seed + 2000, 0.5, ex, F.soft * 1.6, 0.15, 0.2);
  const c3 = cells(wx - 23.7, wy + 9.9, F.big, seed + 3000, 0.35, ex * smooth(0.4, 0.8, E), F.soft * 2.4, 0.14, 0.2);
  v += 0.14 * c1 + 0.22 * c2 + 0.3 * c3;
  v += 0.3 * boost;
  return v - 0.11 * f.S[i];
}

function xlSkin(state, hue, w, h, seed, t, opts) {
  const f = xlField(w, h, seed);
  const F = f.F;
  if (state === 'idle') {
    const ramp = rampOf(hue, 64);
    return (x, y, i) => pick(ramp, dermisV(f, seed, i, x, y, 0, false));
  }
  if (state === 'review') {
    // Mottle: irregular leucophore-white blotches and dark patches at two scales over the dermis.
    const ramp = rampOf(hue, 64);
    const A = coarse(w, h, F.step, (x, y) => warped(x / (0.42 * F.macro), y / (0.42 * F.macro), seed + 131, 2.4));
    const B = coarse(w, h, F.step, (x, y) => warped(x / (0.15 * F.macro), y / (0.15 * F.macro), seed + 137, 1.6));
    return (x, y, i) => {
      const light = smooth(0.54, 0.66, A[i]) * (0.55 + 0.45 * smooth(0.4, 0.6, B[i]));
      const dark = smooth(0.43, 0.32, A[i]) * smooth(0.42, 0.6, B[i]);
      const v = dermisV(f, seed, i, x, y, 0.6 * dark, true);
      return pick(ramp, v * (1 - 0.75 * light) + 0.04 * light);
    };
  }
  // working — passing cloud: a soft, ragged dark wave of expanded sacs drifting across at <= 4 fps.
  const ramp = rampOf(hue, 40);
  const tq = opts.reducedMotion ? 0 : Math.floor((t || 0) * 4) / 4;
  const span = w * 1.7, width = 0.32 * w;
  const x0 = 0.45 * w + 2.3 * F.med * tq;
  const L = memo(`w|${seed}|${w}x${h}`, () => {
    const rest = new Float32Array(w * h), full = new Float32Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        rest[i] = dermisV(f, seed, i, x + 0.5, y + 0.5, 0, false);
        full[i] = dermisV(f, seed, i, x + 0.5, y + 0.5, 1, false);
      }
    return { rest, full };
  });
  return (x, y, i) => {
    const rag = (fbm(x / (1.8 * F.med), y / (1.8 * F.med) + tq * 0.5, seed + 97) - 0.5) * 0.9 * width;
    let d = x + rag - (y - h / 2) * 0.3 - x0;
    d = (((d % span) + span * 1.5) % span) - span / 2; // wrap: the wave re-enters from the left
    const cl = smooth(width, width * 0.15, Math.abs(d));
    return pick(ramp, L.rest[i] + (L.full[i] - L.rest[i]) * cl);
  };
}

/** XL eyespot centres: spread over the field, slightly irregular. */
function xlEyes(w, h, f, seed, n) {
  const out = [];
  for (let k = 0; k < n; k++) {
    const fx = 0.26 + 0.48 * ((k + 0.5) / n) + 0.12 * (h2(k, 1, seed + 301) - 0.5);
    const fy = 0.22 + 0.56 * h2(k, 2, seed + 301);
    const r = (15 + 8 * h2(k, 3, seed + 301)) * f.u;
    out.push({ x: fx * w, y: fy * h, rx: r * (1.02 + 0.2 * h2(k, 4, seed + 301)), ry: r, p: 6.28 * h2(k, 5, seed + 301), s: seed + 311 + k });
  }
  return out;
}
/** Normalised distance to an eyespot centre, with a hashed wobble so the outline is never a perfect ellipse. */
function eyeDist(e, x, y, k) {
  const dx = (x - e.x) / e.rx, dy = (y - e.y) / e.ry;
  const a = Math.atan2(dy, dx);
  const wob = 1 + 0.09 * Math.sin(3 * a + e.p) + 0.06 * Math.sin(5 * a + 2 * e.p) + 0.05 * (vnoise(x / (6 * k), y / (6 * k), e.s) - 0.5);
  return Math.hypot(dx, dy) / wob;
}
const shadeC = (c, s) => (s >= 0 ? mixC(c, [255, 255, 255], 0.25 * Math.min(1, s)) : mixC(c, [0, 0, 0], 0.35 * Math.min(1, -s)));

function xlZebra(hue, w, h, seed) {
  // Sepia "intense zebra": wavy, tapering bands of fully expanded sacs across the body; amber eyespots on top.
  const f = xlField(w, h, seed);
  const F = f.F;
  const ramp = rampOf(hue, 64);
  const per = 3.0 * F.med;
  const eyes = xlEyes(w, h, f, seed, 3);
  const bend = coarse(w, h, F.step, (x, y) => warped(x / (0.38 * F.macro), y / (0.38 * F.macro), seed + 171, 2.0));
  const duty = coarse(w, h, F.step, (x, y) => fbm(x / (0.45 * F.macro), y / (0.2 * F.macro) + 4, seed + 177));
  const skin = (x, y, i) => {
    const ph = (x + (y - h / 2) * 0.22) / per + 1.4 * (bend[i] - 0.5) * 2;
    const taper = 0.3 + 0.24 * duty[i]; // band width swells and tapers along the body
    const b = smooth(taper + 0.09, taper - 0.09, ph - Math.floor(ph));
    return pick(ramp, dermisV(f, seed, i, x, y, 0.6 * b, false) + 0.3 * b);
  };
  return (x, y, i) => {
    for (const e of eyes) {
      const d = eyeDist(e, x, y, f.u);
      if (d < 1.3) {
        const c = shadeC(rings(d, [[0, INK], [0.34, AMBER], [0.7, AMBER_DEEP], [0.95, INK]], 0.06), 0.8 * f.S[i] + 1.2 * f.gran[i]);
        return d < 1.18 ? c : mixC(c, skin(x, y, i), smooth(1.18, 1.3, d));
      }
    }
    return skin(x, y, i);
  };
}

function xlDeimatic(w, h, seed) {
  // The body blanches pale (sacs retract to specks), two dark-ringed spots flash, the margins flush red.
  const f = xlField(w, h, seed);
  const F = f.F;
  const eyes = xlEyes(w, h, f, seed, 2);
  const edge = 0.13 * Math.min(w, h);
  return (x, y, i) => {
    const s = f.S[i] + 1.5 * f.gran[i];
    for (const e of eyes) {
      const d = eyeDist(e, x, y, f.u);
      if (d < 1.25) return shadeC(rings(d, [[0, BLANCH[6]], [0.45, INK], [0.9, RED_DEEP], [1.12, BLANCH[4]]], 0.06), s);
    }
    const rag = (warped(x / (2.2 * F.med), y / (2.2 * F.med), seed + 191, 2.2) - 0.5) * 3.2 * edge;
    const dEdge = Math.min(x, w - x) * 0.9 + Math.min(y, h - y) * 0.35 + rag;
    const sp = cells(x + 0.9 * F.med * f.qx[i], y + 0.9 * F.med * f.qy[i], F.med * 0.8, seed + 211, 0.55, 0.45, F.soft, 0.16, 0.2);
    const pale = pick(BLANCH, 0.08 + 0.14 * (f.macro[i] - 0.5) + 0.25 * f.gran[i] + 0.22 * sp - 0.12 * f.S[i]);
    const red = shadeC(dEdge < edge * 0.4 ? RED_DEEP : RED, s);
    return mixC(pale, red, smooth(edge, edge * 0.65, dEdge));
  };
}

function xlHatch(w, h, seed) {
  // Neutral wavy hatch: diagonal threads bent by a warped field (no straight lines), greys only, lit relief.
  const f = xlField(w, h, seed);
  const F = f.F;
  const per = 1.4 * F.med;
  const wv = coarse(w, h, F.step, (x, y) => warped(x / (0.6 * F.macro), y / (0.6 * F.macro), seed + 5, 2.2));
  return (x, y, i) => {
    const ph = (x + y * 1.1) / per + 1.3 * (wv[i] - 0.5) * 2;
    const s = Math.sin(ph * Math.PI * 2);
    return pick(GREYS, 0.25 + 0.5 * smooth(-0.6, 0.6, s) + 0.3 * (f.macro[i] - 0.5) + 0.15 * f.gran[i] - 0.3 * f.S[i]);
  };
}

function xlPattern(state, hue, w, h, seed, t, opts) {
  if (state === 'fault') return xlDeimatic(w, h, seed);
  if (hue === null || state === 'unknown') return xlHatch(w, h, seed);
  if (state === 'needs-you') return xlZebra(hue, w, h, seed);
  return xlSkin(state, hue, w, h, seed, t, opts);
}

// ================================================================ M / S: the same grammar, posterised
/** Alarm eyespot centres along a strip (world coords, strip height 4), clear of the text at the left. */
function stripEyes(w, seed, tiny) {
  if (tiny) return [{ x: w - 1.5, y: 2, rx: 1.35, ry: 1.25, pupil: false }];
  const n = Math.max(1, Math.min(4, Math.floor((w - 12) / 26)));
  const x0 = w <= 30 ? w * 0.72 : Math.max(24, w * 0.3);
  const x1 = w - 5;
  const out = [];
  for (let k = 0; k < n; k++) {
    const f = n === 1 ? 0.5 : k / (n - 1);
    out.push({ x: x0 + (x1 - x0) * f + 2 * (h2(k, 5, seed + 307) - 0.5), y: 2, rx: 3.1, ry: 2.25, pupil: true });
  }
  return out;
}

/**
 * At M and S a strip is 1-4 logical px tall, so the dermis is drawn as a bold graphic: flat identity tones (light,
 * ground, mid, deep, ink), crisp shapes, hashed rhythm (sizes and gaps vary, nothing tiles). World y spans 0..4
 * on every rung (the bg rung samples every other half-rung row), so a state reads the same on both rungs.
 */
function stripPattern(state, hue, w, seed, t, opts) {
  const tiny = w <= 8;
  if (hue === null || state === 'unknown') {
    const g0 = GREYS[30], g1 = GREYS[12]; // neutral wavy hatch, two greys
    return (x, y) => {
      const ph = (x + 1.15 * y) / (tiny ? 2.6 : 4.6) + 0.7 * (warped(x / 13, y / 13, seed + 5, 2.0) - 0.5) * 2;
      return ph - Math.floor(ph) < 0.5 ? g0 : g1;
    };
  }
  if (state === 'fault') {
    // deimatic: blanched strip, ink-ringed red spots, red flush at both ends (wavy inner edge)
    const eyes = stripEyes(w, seed, tiny).slice(0, tiny ? 1 : 3);
    const edge = tiny ? 0.8 : Math.max(2.5, w * 0.05);
    return (x, y) => {
      for (const e of eyes) {
        const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
        if (d < 1.05) return d < 0.45 ? RED : INK;
      }
      const dEdge = Math.min(x, w - x) + (tiny ? 0 : 1.6 * (vnoise(y / 1.3, x < w / 2 ? 0.5 : 7.5, seed + 191) - 0.5));
      return dEdge < edge ? RED : BLANCH[0];
    };
  }
  const ramp = rampOf(hue, 64);
  const T = { light: pick(ramp, 0.1), ground: pick(ramp, 0.34), mid: pick(ramp, 0.52), deep: pick(ramp, 0.72), ink: pick(ramp, 0.97) };
  // stipple: one spot per hashed slot along the strip; three sac sizes at varied heights; some slots stay empty
  const SL = tiny ? 2 : 5.3;
  const spot = (x, y, grow) => {
    const k0 = Math.floor(x / SL);
    for (let k = k0 - 1; k <= k0 + 1; k++) {
      const r0 = h2(k, 0, seed + 11);
      if (r0 > (tiny ? 0.7 : 0.82)) continue;
      let cls = 0;
      if (!tiny && r0 < 0.3) cls = 2;
      else if (!tiny && r0 < 0.58) cls = 1;
      const cx = (k + 0.2 + 0.6 * h2(k, 1, seed + 11)) * SL;
      const cy = cls === 2 ? 2 : 0.8 + 2.4 * h2(k, 2, seed + 11);
      const rx = ([0.62, 1.15, 1.7][cls] + (tiny ? 0 : 0.25 * h2(k, 3, seed + 11))) * grow;
      const ry = [0.62, 1.05, 1.55][cls] * grow;
      const d = Math.hypot((x - cx) / rx, (y - cy) / ry);
      if (d < 1) return cls === 0 || (cls === 1 && d >= 0.55) ? T.deep : T.ink;
    }
    return null;
  };
  if (state === 'idle' && tiny) {
    // the 4x2 swatch: one deep sac on the vivid ground, its place hashed from the session
    const sx = 1 + Math.floor(2 * h2(1, 1, seed + 11)), sy = h2(2, 2, seed + 11) < 0.5 ? 0 : 1;
    return (x, y) => (Math.floor(x) === sx && Math.floor(y) === sy ? T.deep : T.ground);
  }
  if (state === 'idle') return (x, y) => spot(x, y, 1) || T.ground;
  if (state === 'review') {
    // two-scale mottle: pale and dark patches whose size and spacing drift along the body (wavy edges)
    const ph0 = 6.28 * h2(3, 3, seed + 131);
    if (tiny) return (x, y) => (x < 2 && y < 2 ? T.light : x > 2 && y > 2 ? T.deep : T.ground);
    return (x, y) => {
      const a = Math.sin(x / 3.4 + ph0 + 1.3 * Math.sin(x / 9.5 + ph0)) + 0.9 * (warped(x / 9, y / 6, seed + 131, 2.0) - 0.5);
      const tilt = 0.12 * (y - 2);
      if (a > 0.42 + tilt) return T.light;
      if (a < -0.5 - tilt) return T.deep;
      return vnoise(x / 1.7, y / 1.4, seed + 137) > 0.78 ? T.mid : T.ground;
    };
  }
  if (state === 'needs-you') {
    const eyes = stripEyes(w, seed, tiny);
    return (x, y) => {
      for (const e of eyes) {
        const d = Math.hypot((x - e.x) / e.rx, (y - e.y) / e.ry);
        if (d < 1.05) return e.pupil && d < 0.42 ? INK : AMBER;
      }
      if (tiny) return x < 1.5 ? T.ink : T.ground;
      const ph = x / 5.8 + 0.8 * (fbm(x / 19, 0.5, seed + 171) - 0.5) * 2 + 0.12 * y;
      const duty = 0.3 + 0.2 * vnoise(x / 11, 0.5, seed + 177); // bands swell and taper along the body
      return ph - Math.floor(ph) < duty ? T.ink : T.ground;
    };
  }
  // working: the stipple, with a ragged dark cloud (core + fringe) drifting right, <= 4 fps; the swatch moves 1 px/frame
  const tq = opts.reducedMotion ? 0 : Math.floor((t || 0) * 4) / 4;
  const span = tiny ? w : w * 1.35;
  const width = tiny ? 1.2 : 0.11 * w + 3;
  const x0 = (tiny ? 0.5 : 0.45 * w) + (tiny ? w : 5) * tq;
  return (x, y) => {
    const rag = tiny ? 0 : 2.2 * (fbm(x / 6, y / 3 + 3.1, seed + 97) - 0.5) * 2;
    let d = x + rag - x0;
    d = (((d % span) + span * 1.5) % span) - span / 2;
    const a = Math.abs(d);
    const s = spot(x, y, a < width ? 1.35 : 1);
    if (a < width * 0.55) return s ? T.ink : T.deep;
    if (a < width) return s ? T.ink : T.mid;
    return s || T.ground;
  };
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
const KNOWN = new Set(['idle', 'working', 'review', 'needs-you', 'fault', 'unknown']);

export function paint({ scale, w, h, state, session, t, opts }) {
  const o = opts || {};
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const st = KNOWN.has(state) ? state : 'unknown';
  const seed = seedOf(session);
  const px = new Uint8ClampedArray(w * h * 4);
  let fn, sy = 1;
  if (scale === 'XL') fn = xlPattern(st, hue, w, h, seed, t, o);
  else {
    // M / S world height is 4: the 4-row half rung 1:1, the 2-row bg rung (and the 1-row pill on it) every other row
    sy = scale === 'M' ? Math.max(1, 4 / h) : h <= 1 ? 2 : 1;
    fn = stripPattern(st, hue, w, seed, t, o);
  }
  for (let y = 0; y < h; y++) {
    const wy = (y + 0.5) * sy;
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const c = fn(x + 0.5, wy, i);
      px[i * 4] = c[0]; px[i * 4 + 1] = c[1]; px[i * 4 + 2] = c[2]; px[i * 4 + 3] = 255;
    }
  }
  return { pixels: px, text: layoutText(scale, st, session, w) };
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
