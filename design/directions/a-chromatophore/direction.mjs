// Direction A, round 2: "Sepia dermis". Pure ESM: no imports, no timers, no I/O (CONTRACT §2).
//
// One pure skin function, sampled at every scale (plan §13.2). Skin is described in BODY space:
//   a = along the body axis (the long side of every surface), b = across it, in skin units
//   (1 u = one M-scale pixel = one terminal cell column).
// Layers, back to front (Sepia dermis):
//   1. leucophore ground   pale, TINTED in the identity hue, so the hue owns most of every tile (D-R2-1)
//   2. iridophore sheen    thin domain-warped light streaks and white flecks (low chroma, same hue)
//   3. chromatophores      three size classes of pigment sacs, dark identity tones, each organ expanding as a
//                          unit from a per-state, multi-scale, domain-warped expansion field
//   4. relief + light      folds and papillae lit from the upper left, a wet highlight (XL strong, M/S faint)
//   5. XL anatomy          a macro of the dorsal mantle: convex curvature, the pale mantle-edge line and a
//                          rippled translucent fin along one long side
// State = which expansion field drives the sacs; identity = session.hue_deg (OKLCh). Amber and red appear
// only on needs-you / fault. Only working depends on t (the passing cloud), quantised to 4 fps, <= 42 colours.

export const meta = {
  id: 'a-chromatophore',
  name: 'Sepia dermis',
  biology: 'Sepia officinalis dermis (leucophore ground, iridophore sheen, 3 chromatophore size classes): '
    + 'idle=sparse fine sacs in loose rows (stipple), working=passing cloud (soft dark wave of expanded sacs drifting along the body), '
    + 'review=two-scale mottle, needs-you=wavy tapering transverse zebra bands + soft-ringed amber eyespots, '
    + 'fault=deimatic blanch with dark-ringed spots + red margin, unknown=neutral hatch (no identity hue)',
  maxColorsWorking: 48,
  fps: 4,
};

// ---- fixed colours (labels + alarm) ------------------------------------------------------------------
const LABEL_BG = '#1c1b19';
const LABEL_FG = '#f2efe8';
const AMBER_HEX = '#ffc247';
const FAULT_PLATE = '#8f1d17';
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

export function authoredPairs() {
  return [
    { fg: LABEL_FG, bg: LABEL_BG, where: 'name label / unknown ? (dark plate)' },
    { fg: AMBER_HEX, bg: LABEL_BG, where: 'needs-you alarm text INPUT (dark plate)' },
    { fg: '#ffffff', bg: FAULT_PLATE, where: 'fault alarm text ERROR (red plate)' },
  ];
}

// ---- colour: OKLab -> sRGB ------------------------------------------------------------------------------
const toLin = (L, a, b) => {
  let l = L + 0.3963377774 * a + 0.2158037573 * b, m = L - 0.1055613458 * a - 0.0638541728 * b, s = L - 0.0894841775 * a - 1.2914855480 * b;
  l = l * l * l; m = m * m * m; s = s * s * s;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
};
const inGamut = (c) => c[0] >= -1e-4 && c[0] <= 1.0001 && c[1] >= -1e-4 && c[1] <= 1.0001 && c[2] >= -1e-4 && c[2] <= 1.0001;
const enc = (v) => { const x = v < 0 ? 0 : v > 1 ? 1 : v; return Math.round(255 * (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055)); };
// Out-of-gamut colours keep L and hue and lose chroma; the fitting chroma is memoised per (L, hue) bucket.
const GAMUT = new Map();
function labRgb(L, a, b) {
  L = L < 0 ? 0 : L > 1 ? 1 : L;
  let c = toLin(L, a, b);
  if (!inGamut(c)) {
    const C = Math.sqrt(a * a + b * b), key = Math.round(L * 400) * 1000 + Math.round(Math.atan2(b, a) * 120);
    let maxC = GAMUT.get(key);
    if (maxC === undefined) {
      let lo = 0, hi = C;
      for (let i = 0; i < 14; i++) { const m = (lo + hi) / 2; if (inGamut(toLin(L, a * m / C, b * m / C))) lo = m; else hi = m; }
      maxC = lo; if (GAMUT.size < 200000) GAMUT.set(key, maxC);
    }
    const kk = Math.min(1, maxC / C);
    c = toLin(L, a * kk, b * kk);
  }
  return [enc(c[0]), enc(c[1]), enc(c[2])];
}
const mixInto = (o, t, k) => { o[0] += (t[0] - o[0]) * k; o[1] += (t[1] - o[1]) * k; o[2] += (t[2] - o[2]) * k; };
const polarLab = (L, C, hDeg) => { const h = (hDeg * Math.PI) / 180; return [L, C * Math.cos(h), C * Math.sin(h)]; };

// The leucophore ground sits where this hue has the most chroma to give (L in [0.72, 0.80]): identity is read
// from the tile's median colour (G2), so the tint must be as strong as the gamut allows for every hue.
function groundLightness(H) {
  if (H == null) return 0.745;
  const ca = Math.cos((H * Math.PI) / 180), sa = Math.sin((H * Math.PI) / 180);
  let best = 0.745, bestC = -1;
  for (let L = 0.72; L <= 0.8001; L += 0.02) {
    let lo = 0, hi = 0.4;
    for (let i = 0; i < 16; i++) { const m = (lo + hi) / 2; if (inGamut(toLin(L, m * ca, m * sa))) lo = m; else hi = m; }
    if (lo > bestC + 1e-3) { bestC = lo; best = L; }
  }
  return best;
}

// ---- deterministic noise (seeded from session.lineage_id; never Math.random) ----------------------------
function hash(x, y, s) {
  let n = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(s | 0, 1442695041);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x, y, s) {
  const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash(x0, y0, s), b = hash(x0 + 1, y0, s), c = hash(x0, y0 + 1, s), d = hash(x0 + 1, y0 + 1, s);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function fbm(x, y, s, oct = 3) {
  let sum = 0, amp = 0.5, norm = 0;
  for (let i = 0; i < oct; i++) { sum += amp * vnoise(x, y, s + i * 101); norm += amp; x = x * 2.03 + 17.1; y = y * 2.03 - 9.7; amp *= 0.5; }
  return sum / norm;
}
const sstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const frac = (x) => x - Math.floor(x);
const seedOf = (session) => {
  const id = (session && session.lineage_id) || 'unbound';
  let n = 7;
  for (let i = 0; i < id.length; i++) n = (Math.imul(n, 31) + id.charCodeAt(i)) | 0;
  return n;
};

// ---- the chromatophore organ: three size classes on jittered lattices ------------------------------------
// sp = lattice pitch (u), r0 = punctate (retracted) radius, r1 = fully expanded radius, L/C = pigment tone.
const CLASSES = [
  { sp: 2.3, r0: 0.10, r1: 1.05, L: 0.25, C: 0.085, s: 11 },  // large, darkest
  { sp: 1.35, r0: 0.08, r1: 0.62, L: 0.36, C: 0.105, s: 23 }, // medium
  { sp: 0.78, r0: 0.06, r1: 0.34, L: 0.50, C: 0.115, s: 37 }, // small, fine stipple
];
const CLOUD_GAIN = [1.05, 0.95, 0.7];   // working: extra expansion per class at cloud = 1

// ---- XL anatomy (body space): mantle midline, mantle edge, fin -------------------------------------------
function anatomy(ctx) {
  if (ctx.sc !== 'XL') return null;
  const { visB, seed } = ctx;
  return {
    mid: visB * 0.30,
    edge: (a) => visB * 0.80 + 1.1 * Math.sin(a * 0.09 + 0.7) + 1.4 * (fbm(a * 0.05, 3.3, seed + 501, 2) - 0.5),
    fin: (a) => visB * 0.965 + 0.9 * Math.sin(a * 0.42 + 1.1) + 0.5 * Math.sin(a * 1.1),
  };
}

// ---- per-state skin model (body space) ----------------------------------------------------------------------
// E(u, v) -> [El, Em, Es] expansion at a sac centre; ground(u, v) -> [L, C, sheenGain]
function grainField(ctx) {
  const { seed } = ctx;
  return (u, v) => {
    const x = u + 2.5 * (fbm(u * 0.08, v * 0.08, seed + 91, 2) - 0.5), y = v + 2.5 * (fbm(u * 0.08 + 31.7, v * 0.08 - 7.3, seed + 98, 2) - 0.5);
    // isotropic pebbled grain (dermal papillae), no dominant orientation: a periodic stripe read as "ribbed / mechanical"
    return sstep(0.42, 0.72, 0.65 * vnoise(x * 0.85, y * 0.85, seed + 93) + 0.35 * vnoise(x * 1.9, y * 1.9, seed + 95));
  };
}
function model(state, ctx) {
  const { seed, sc } = ctx;
  const warp = (u, v, f, A, s) => [u + A * (fbm(u * f, v * f, seed + s, 2) - 0.5), v + A * (fbm(u * f + 31.7, v * f - 7.3, seed + s + 7, 2) - 0.5)];
  const tonus = (u, v) => { const [x, y] = warp(u, v, 0.06, 14, 3); return fbm(x * 0.09, y * 0.09, seed + 5); };

  if (state === 'idle' || state === 'working') {
    // stipple: most sacs retracted; the expanded few gather in loose, wavy transverse rows (the way a resting
    // Sepia's fine spots follow the skin's growth lines), so the stipple has rhythm instead of noise
    const rows = (u, v) => { const [x, y] = warp(u, v, 0.09, 4, 13); return 0.5 + 0.5 * Math.sin((x * 0.8 + y * 0.6 + 1.6 * Math.sin(y * 0.33)) * 1.3); };
    return {
      E: (u, v) => {
        const T = tonus(u, v), R = rows(u, v);
        const pm = 0.04 + 0.7 * sstep(0.62, 0.95, R), ps = 0.08 + 0.5 * sstep(0.5, 0.95, R);
        const em = hash(Math.floor(u * 7.1), Math.floor(v * 7.1), seed + 98) < pm ? 0.7 + 0.3 * T : 0.05 + 0.2 * T;
        const es = hash(Math.floor(u * 7.1), Math.floor(v * 7.1), seed + 99) < ps ? 0.85 : 0.18 + 0.3 * T;
        return [0.03 + 0.14 * T, em, es];
      },
      ground: (u, v) => [ctx.Lbase - 0.015 + 0.08 * (tonus(u, v) - 0.5) + (sc === 'XL' ? 0.14 * (rows(u, v) - 0.5) + 0.04 * (fbm(u * 0.4, v * 0.4, seed + 9, 2) - 0.5) : 0), 0.15, 1],
    };
  }
  if (state === 'review') {
    // mottle: dark blotches repeated across the mantle on a loose lattice (warped, irregular outlines), with small
    // pale dapples between them: two scales, evenly spread, never the same twice (Sepia "mottle" body pattern)
    const q = sc === 'XL' ? 1.6 : 1;
    const blot = (u, v, sp, s0) => {
      const [x, y] = warp(u, v, 0.25 / q, 1.6 * q, s0);
      const i0 = Math.floor(x / sp), j0 = Math.floor(y / sp);
      let best = 0;
      for (let j = j0 - 1; j <= j0 + 1; j++) for (let i = i0 - 1; i <= i0 + 1; i++) {
        const cx = (i + 0.2 + 0.6 * hash(i, j, s0 + 1)) * sp, cy = (j + 0.2 + 0.6 * hash(i, j, s0 + 2)) * sp;
        const r = sp * (0.2 + 0.16 * hash(i, j, s0 + 3)), dx = (x - cx) / 1.2, dy = y - cy;
        best = Math.max(best, sstep(r, r * 0.7, Math.sqrt(dx * dx + dy * dy)));
      }
      return best;
    };
    const big = (u, v) => blot(u, v, 6.5 * q, seed + 51);
    const dapple = (u, v) => blot(u + 1.7, v + 0.9, 2.6 * q, seed + 61);
    return {
      E: (u, v) => {
        const B = big(u, v), d = dapple(u, v) * (1 - B);
        return [B, Math.max(B, 0.2), 0.25 + 0.65 * B - 0.25 * d];
      },
      ground: (u, v) => {
        const B = big(u, v), d = dapple(u, v) * (1 - B);
        return [0.76 - 0.14 * B + 0.12 * d, 0.13 - 0.05 * d, 1 + 0.5 * d];
      },
    };
  }
  if (state === 'needs-you') {
    // zebra: wavy, tapering transverse bands (dark expanded sacs) on a white leucophore ground
    const P = 6.4;
    const band = (u, v) => {
      const [x, y] = warp(u, v, 0.05, sc === 'XL' ? 10 : 6, 71);
      // bands meet the dorsal midline as shallow chevrons, as Sepia zebra bands do
      const chev = (sc === 'XL' ? 0.55 : 1.4) * Math.abs(v - ctx.grid.oy - ctx.midB);
      const f = frac((x + chev + (sc === 'XL' ? 2.2 : 1.2) * Math.sin(y * 0.16 + (seed & 7))) / P);
      const duty = 0.28 + 0.26 * fbm(x * 0.05, y * 0.05, seed + 73);   // taper: the band thins along its length
      const e = 0.09;
      return Math.min(1, sstep(-e, e, f) * (1 - sstep(duty - e, duty + e, f)) + sstep(1 - e, 1 + e, f));
    };
    return {
      E: (u, v) => { const z = band(u, v); return [z, z, 0.15 + 0.7 * z]; },
      ground: (u, v) => { const z = band(u, v); return [0.87 - 0.40 * z, 0.06 + 0.06 * z, 1.4 * (1 - z)]; },
    };
  }
  if (state === 'fault') {
    // deimatic: sudden blanch, every sac snaps to a pinpoint (still visible as faint specks)
    return {
      E: () => [0, 0, 0],
      ground: (u, v) => [0.95 - 0.035 * fbm(u * 0.1, v * 0.1, seed + 81), 0.024, 0.5],
    };
  }
  // unknown / degraded: neutral, a warped diagonal hatch, no identity hue at all
  const hatch = (u, v) => {
    const [x, y] = warp(u, v, 0.06, 1.4, 91);
    const f = frac((x + y * 1.4) / (sc === 'XL' ? 3.4 : 6.0));
    return sstep(0.1, 0.22, f) * (1 - sstep(0.48, 0.6, f));
  };
  return {
    E: (u, v) => { const q = hatch(u, v); return [0.04, 0.8 * q, 0.15 + 0.6 * q]; },
    ground: (u, v) => [0.82 - 0.2 * hatch(u, v), 0, 0.3],
  };
}

// ---- working: the passing cloud, a soft dark wave of expanded sacs drifting along the body ------------------
// Two waves half a span apart, so one is always in view. Its value c in [0,1] expands every sac toward full
// and darkens the ground; it is the only thing that depends on t.
function cloudField(ctx) {
  const { seed, tq, visA, visB, sc } = ctx;
  const wc = Math.max(1.6, Math.min(16, visA * 0.3));
  const span = visA + 2.4 * wc, period = sc === 'Ss' ? 2 : sc === 'S' ? 4 : sc === 'XL' ? 10 : 20;
  const ph = ((tq / period) + 0.27 + (((seed >>> 3) & 15) / 160)) % 1;
  const centres = [ph, (ph + 0.5) % 1].map((p) => p * span - 1.2 * wc);
  const bend = Math.min(visB * 0.35, 10);
  return (u, v) => {
    const x = u + 6 * (fbm(u * 0.08, v * 0.08, seed + 41, 2) - 0.5), y = v + 6 * (fbm(u * 0.08 + 5, v * 0.08, seed + 48, 2) - 0.5);
    let c = 0;
    for (const c0 of centres) {
      const d = (x - c0 - bend * Math.sin(y * 0.11 + 1.3)) / wc;
      c = Math.max(c, Math.exp(-d * d * 2.2));
    }
    return c * (0.75 + 0.25 * vnoise(u * 0.3, v * 0.3, seed + 43));
  };
}

// ---- alarm overlays (body space): eyespots, ring spots, red margin ----------------------------------------------
function eyeList(state, ctx, freeA) {
  const { visA, visB, sc, seed } = ctx;
  if ((state !== 'needs-you' && state !== 'fault') || sc === 'Ss') return [];
  if (sc === 'XL') {
    const r = visB * 0.14, out = [];
    // two eyespots on the mantle, between midline and edge; deimatic adds smaller ring spots
    for (const fa of [0.33, 0.66]) out.push({ a: fa * visA, b: visB * 0.5, rx: r, ry: r * 0.92 });
    if (state === 'fault') for (const [fa, fb] of [[0.16, 0.3], [0.5, 0.24], [0.84, 0.32], [0.24, 0.66], [0.78, 0.68]]) out.push({ a: fa * visA, b: fb * visB, rx: r * 0.5, ry: r * 0.46 });
    return out;
  }
  const ry = visB <= 2 ? 1.25 : visB * 0.5, rx = visB <= 2 ? 2.4 : ry * 1.35;
  const room = visA - freeA - (state === 'fault' ? 3 : 0);
  if (state === 'fault' && room >= 18) {   // deimatic: a loose row of dark-ringed spots of varied size
    const out = [], n = Math.max(2, Math.min(3, Math.floor(room / 22)));
    for (let i = 0; i < n; i++) {
      const s = 0.75 + 0.35 * hash(i, 3, seed + 601);
      out.push({ a: freeA + room * (i + 0.5 + 0.25 * (hash(i, 4, seed + 602) - 0.5)) / n, b: visB / 2, rx: rx * s, ry: ry * Math.min(1, s) });
    }
    return out;
  }
  if (room >= 4 * rx + 8) return [{ a: freeA + room * 0.3, b: visB / 2, rx, ry }, { a: freeA + room * 0.3 + 2 * rx + 5, b: visB / 2, rx, ry }];
  if (room >= 2 * rx + 1.5) return [{ a: visA - (state === 'fault' ? 3 : 0) - rx - 0.8, b: visB / 2, rx, ry }];
  return [];
}

const AMBER_LAB = polarLab(0.83, 0.165, 75);
const RED_LAB = polarLab(0.53, 0.19, 29);
const RING_LAB = [0.2, 0, 0];

function overlay(state, eyes, lab, u, v, ctx) {
  for (const e of eyes) {
    const du = (u - e.a) / e.rx, dv = (v - e.b) / e.ry;
    // a slightly irregular outline: real eyespots are not compass circles
    const d = Math.sqrt(du * du + dv * dv) * (1 + 0.06 * Math.sin(Math.atan2(dv, du) * 3 + e.a));
    if (d > 1.4) continue;
    if (state === 'needs-you') {
      mixInto(lab, [0.93, lab[1] * 0.3, lab[2] * 0.3], (1 - sstep(1.0, 1.4, d)) * 0.85);   // pale halo
      mixInto(lab, RING_LAB, sstep(1.0, 0.82, d) * sstep(0.40, 0.58, d));                  // soft dark ring
      const core = 1 - sstep(0.40, 0.58, d);
      if (core > 0) mixInto(lab, [AMBER_LAB[0] + 0.06 - 0.16 * d, AMBER_LAB[1], AMBER_LAB[2]], core);   // amber iris
    } else {
      mixInto(lab, RING_LAB, sstep(1.08, 0.86, d) * sstep(0.42, 0.62, d));                 // dark ring, blanched centre
    }
  }
  if (state === 'fault') {
    // red margin: the far end at M/S, the whole rim at XL (a flush that fades inward)
    const { visA, visB, sc } = ctx;
    const m = sc === 'XL' ? visB * 0.07 : 2.4;
    const de = sc === 'XL' ? Math.min(u, v, visA - u, visB - v) : visA - u;
    const k = 1 - sstep(m * 0.45, m * 1.1, de + 0.3 * m * (vnoise(u * 0.4, v * 0.4, 5) - 0.5));
    if (k > 0) mixInto(lab, RED_LAB, k);
  }
}

// ---- static layers (body space), split by frequency -----------------------------------------------------------
// ground: leucophore + sheen + anatomy, OKLab per pixel. cov[ci]: chromatophore coverage per class on the
// ss x ss subsample grid (each organ scatter-rasterised once; most are punctate, so this is cheap).
// working also keeps covFull (the same organs fully expanded by the cloud); a frame blends the two.
function buildLayers(state, H, ctx) {
  const mdl = model(state === 'working' ? 'idle' : state, ctx);
  const hr = H == null ? 0 : (H * Math.PI) / 180, ca = Math.cos(hr) * ctx.chroma, sa = Math.sin(hr) * ctx.chroma;
  const neutral = H == null || state === 'unknown';
  const { seed, aa, an } = ctx;
  const { bw, bh, k, ss, ox, oy } = ctx.grid, SW = bw * ss, SH = bh * ss, step = k / ss;
  const withFull = state === 'working';
  const cov = CLASSES.map(() => new Float32Array(SW * SH));
  const covFull = withFull ? CLASSES.map(() => new Float32Array(SW * SH)) : null;
  const tone = CLASSES.map((K) => {
    const C = neutral ? 0 : K.C, L = state === 'fault' ? Math.min(0.8, K.L + 0.3) : K.L;
    return [L, C * ca, C * sa];
  });
  const disc = (buf, cx, cy, r) => {
    const R = r + aa;
    const x0 = Math.max(0, Math.floor((cx - R) / step - 0.5)), x1 = Math.min(SW - 1, Math.ceil((cx + R) / step - 0.5));
    const y0 = Math.max(0, Math.floor((cy - R) / step - 0.5)), y1 = Math.min(SH - 1, Math.ceil((cy + R) / step - 0.5));
    for (let y = y0; y <= y1; y++) {
      const dy = (y + 0.5) * step - cy;
      for (let x = x0; x <= x1; x++) {
        const dx = (x + 0.5) * step - cx;
        let c = (r - Math.sqrt(dx * dx + dy * dy)) / aa + 0.5;
        if (c <= 0) continue;
        if (c > 1) c = 1;
        const n = y * SW + x;
        if (c > buf[n]) buf[n] = c;
      }
    }
  };
  const grainSac = grainField(ctx);
  const u1 = ox + bw * k, v1 = oy + bh * k;
  CLASSES.forEach((K, ci) => {
    const i0 = Math.floor(ox / K.sp) - 1, j0 = Math.floor(oy / K.sp) - 1, i1 = Math.floor(u1 / K.sp) + 1, j1 = Math.floor(v1 / K.sp) + 1;
    for (let J = j0; J <= j1; J++) for (let I = i0; I <= i1; I++) {
      const su = (I + 0.1 + 0.8 * hash(I, J, seed + K.s)) * K.sp, sv = (J + 0.1 + 0.8 * hash(I, J, seed + K.s + 1)) * K.sp;
      const pa = su - ox, pb = sv - oy;
      if (ctx.mirror && pb > ctx.midB + K.sp) continue;               // bilateral: one half is grown, the other mirrors it
      let fade = 1;
      if (an) { const ed = an.edge(pa); if (pb > ed + 0.3) continue; fade = sstep(ed + 0.3, ed - 1.2, pb); }   // no sacs on the fin
      const e = Math.min(1, Math.max(0, mdl.E(su, sv)[ci] + (ci > 0 && ctx.grainAmp ? ctx.grainAmp * 0.55 * grainSac(su, sv) : 0)));
      const mat = (0.7 + 0.45 * hash(I, J, seed + K.s + 2)) * fade;      // organ-to-organ size variation
      const radius = (x) => (K.r0 + (K.r1 - K.r0) * x ** 1.25) * mat;
      for (const b of ctx.mirror ? [pb, 2 * ctx.midB - pb] : [pb]) {
        disc(cov[ci], pa, b, radius(e));
        if (withFull) disc(covFull[ci], pa, b, radius(Math.min(1, e + CLOUD_GAIN[ci])));
      }
    }
  });
  // ground per pixel (+ the XL anatomy)
  const grain = grainField(ctx);
  const ground = new Float32Array(bw * bh * 3);
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
    const pa = (x + 0.5) * k, pb = (y + 0.5) * k, u = pa + ox, v = (ctx.mirror ? Math.min(pb, 2 * ctx.midB - pb) : pb) + oy;
    const [gL0, gC, sheenGain] = mdl.ground(u, v);
    const gq = ctx.grainAmp ? grain(u, v) : 0, gL = gL0 - ctx.grainAmp * 0.2 * gq;
    // XL: slow hue drift (+-10 deg), clamped inside the identity arc so it never strays toward amber/red
    const hj = an && !neutral ? (Math.min(Math.max(H, 328), Math.max(Math.min(H, 122), H + (fbm(u * 0.03, v * 0.03, seed + 401, 2) - 0.5) * 20)) - H) * Math.PI / 180 : 0;
    const C0 = neutral ? 0 : gC * ctx.chroma, cj = Math.cos(hr + hj), sj = Math.sin(hr + hj);
    const lab = [gL, C0 * cj, C0 * sj];
    if (sheenGain > 0) {   // iridophore sheen: thin warped streaks + leucophore flecks (pale, low chroma, same hue)
      const qx = u + 4 * (fbm(u * 0.07, v * 0.07, seed + 201, 2) - 0.5), qy = v + 4 * (fbm(u * 0.07 + 9, v * 0.07, seed + 203, 2) - 0.5);
      const st = Math.abs(Math.sin((qx * 0.55 + qy * 0.9) * 0.9 + 3 * vnoise(qx * 0.12, qy * 0.12, seed + 205)));
      const streak = sstep(0.93, 0.995, st) * sstep(0.45, 0.7, vnoise(qx * 0.05, qy * 0.05, seed + 207));
      const fl = hash(Math.floor(u * 2.2), Math.floor(v * 2.2), seed + 209) < 0.035 ? 0.7 : 0;
      const kk = Math.min(0.75, (0.5 * streak + fl) * sheenGain * ctx.detail);
      if (kk > 0) mixInto(lab, [Math.min(0.97, gL + 0.16), lab[1] * 0.45, lab[2] * 0.45], kk);
    }
    if (an) {
      const ed = an.edge(pa), fe = an.fin(pa);
      const line = sstep(1.1, 0.2, Math.abs(pb - ed + 0.2));          // pale mantle-edge line along the fin base
      if (line > 0) mixInto(lab, [0.95, lab[1] * 0.2, lab[2] * 0.2], line * 0.9);
      if (pb > ed + 0.5) {
        // fin: translucent, rippled, fine rays; darkens toward its free edge; dark water beyond
        const t2 = (pb - ed) / Math.max(1, fe - ed);
        const ray = 0.5 + 0.5 * Math.sin(pa * 2.6 + pb * 0.6 + 2 * vnoise(pa * 0.2, pb * 0.2, seed + 511));
        const fl = 0.66 - 0.2 * t2 + 0.05 * ray + 0.07 * Math.sin(pa * 0.42 + 1.1);
        mixInto(lab, neutral ? [fl, 0, 0] : polarLab(fl, 0.05 * ctx.chroma, H + hj * 57.3), sstep(ed + 0.5, ed + 1.6, pb));
        const rim = sstep(0.9, 0.1, Math.abs(pb - fe));
        if (rim > 0) mixInto(lab, [0.88, lab[1] * 0.4, lab[2] * 0.4], rim * 0.7);
        if (pb > fe) mixInto(lab, neutral ? [0.13, 0, 0] : polarLab(0.14, 0.025 * ctx.chroma, H), sstep(fe, fe + 0.6, pb));
      }
    }
    const n = (y * bw + x) * 3;
    ground[n] = lab[0]; ground[n + 1] = lab[1]; ground[n + 2] = lab[2];
  }
  // relief: a height field (folds + papillae + XL body curvature) lit from the upper left -> diffuse shade
  // and a wet specular highlight. Strong at XL (the depth of a macro photograph), faint at M/S.
  const shade = new Float32Array(bw * bh).fill(1), spec = new Float32Array(bw * bh);
  const relief = ctx.relief;
  if (relief > 0) {
    const HW = bw + 2, hf = new Float32Array(HW * (bh + 2));
    const pap = (u, v) => {
      const sp = 2.6, i0 = Math.floor(u / sp), j0 = Math.floor(v / sp);
      let best = 0;
      for (let j = j0 - 1; j <= j0 + 1; j++) for (let i = i0 - 1; i <= i0 + 1; i++) {
        const r = hash(i, j, seed + 301);
        if (r > 0.55) continue;
        const cx = (i + 0.2 + 0.6 * hash(i, j, seed + 302)) * sp, cy = (j + 0.2 + 0.6 * hash(i, j, seed + 303)) * sp;
        const rad = 0.55 + 0.7 * r, dx = u - cx, dy = v - cy, q = (dx * dx + dy * dy) / (rad * rad);
        if (q < 1) best = Math.max(best, (1 - q) * (1 - q));
      }
      return best;
    };
    for (let y = -1; y <= bh; y++) for (let x = -1; x <= bw; x++) {
      const pa = (x + 0.5) * k, pb = (y + 0.5) * k, u = pa + ox, v = (ctx.mirror ? Math.min(pb, 2 * ctx.midB - pb) : pb) + oy;
      const fx = u + 5 * (fbm(u * 0.05, v * 0.05, seed + 311, 2) - 0.5);
      let hh = 1.0 * fbm(fx * 0.075, (v + 4 * (fbm(u * 0.04 + 9.1, v * 0.04, seed + 319, 2) - 0.5)) * 0.075, seed + 313, 3) + 0.35 * pap(u, v) + ctx.grainAmp * 0.5 * grain(u, v) + 0.1 * vnoise(u * 1.3, v * 1.3, seed + 317);
      if (an) {   // convex mantle: a dome across the body, falling away past the edge onto the fin
        const ed = an.edge(pa), q = (pb - an.mid) / (ed - an.mid);
        hh += pb < ed ? 6 * (1 - q * q) : -0.8 * (pb - ed);
      }
      hf[(y + 1) * HW + x + 1] = hh;
    }
    const lx = -0.45, ly = -0.65, lz = 0.62, hx = lx, hy = ly, hz = lz + 1, hn = Math.sqrt(hx * hx + hy * hy + hz * hz);
    for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
      const c = (y + 1) * HW + x + 1;
      const gx = (hf[c + 1] - hf[c - 1]) / (2 * k), gy = (hf[c + HW] - hf[c - HW]) / (2 * k);
      const nx = -gx * 1.4, ny = -gy * 1.4, nn = Math.sqrt(nx * nx + ny * ny + 1);
      const dif = (nx * lx + ny * ly + lz) / nn, nh = (nx * hx + ny * hy + hz) / (nn * hn);
      shade[y * bw + x] = 1 + relief * 0.55 * (dif - lz);
      spec[y * bw + x] = relief * 0.3 * Math.pow(Math.max(0, nh), 24);
    }
  }
  return { ground, cov, covFull, tone, shade, spec, kmix: state === 'fault' ? 0.6 : 0.96 };
}

// ---- text layout (cells for M/S, CSS px for XL) -------------------------------------------------------------------
function layout(scale, w, h, state, session, degraded, opts) {
  const text = [], plates = [];
  if (scale === 'S' && w <= 8) return { text, plates, free: 0 };   // desktop swatch: no text (D-R2-2)
  const name = degraded ? 'unbound' : session.name;
  const alarm = session.alarm_text;
  const tag = state === 'unknown' ? '?' : (state === 'needs-you' || state === 'fault') ? alarm : null;
  const tagStyle = state === 'needs-you' ? { fg: AMBER_HEX, bg: LABEL_BG }
    : state === 'fault' ? { fg: '#ffffff', bg: FAULT_PLATE } : { fg: LABEL_FG, bg: LABEL_BG };
  const nameStyle = { fg: LABEL_FG, bg: LABEL_BG };
  if (scale === 'XL') {
    const cssH = (opts && opts.cssH) || h * 4;
    if (tag) text.push({ x: 16, y: cssH - 44, str: tag, ...tagStyle });
    return { text, plates, free: 0 };
  }
  const nm = name.slice(0, Math.max(1, Math.min(10, w - 4)));
  const rowH = h >= 4 ? h / 2 : h;
  let end = 0;
  const add = (str, col, row, st) => {
    text.push({ x: col, y: row, str, ...st });
    const y0 = Math.floor(row * rowH), y1 = Math.min(h, Math.ceil((row + 1) * rowH));
    plates.push({ x0: col - 1, y0, x1: col + str.length + 1, y1, c: hexRgb(st.bg) });
    end = Math.max(end, col + str.length + 1);
  };
  if (h >= 4) {
    if (tag && 1 + tag.length + 1 <= w) add(tag, 1, 0, tagStyle);
    add(nm, 1, 1, nameStyle);
  } else {
    add(nm, 1, 0, nameStyle);
    if (tag && end + 1 + tag.length + 1 <= w) add(tag, end + 1, 0, tagStyle);
    else if (tag && scale === 'S') { text.length = 0; plates.length = 0; end = 0; add(tag, 1, 0, tagStyle); }
  }
  return { text, plates, free: end + 1 };
}

// ---- working palette: <= 48 colours, all on the identity hue ---------------------------------------------------------
const WL = 14, WC = [0.025, 0.075, 0.125];   // 14 lightness x 3 chroma steps = 42 colours

// Static layers (and static frames) are memoised per (scale, size, state, session): the same arguments always
// give the same bytes, and a working frame at 4 fps only pays for the cloud and the blend.
const MEMO = new Map();
const MEMO_MAX = 24;

// ---- paint -------------------------------------------------------------------------------------------------------
export function paint({ scale, w, h, state, session, t = 0, opts = {} }) {
  const degraded = session.hue_deg == null;
  const H = degraded ? null : session.hue_deg;
  const seed = seedOf(session);
  const working = state === 'working';
  const moving = working && !opts.reducedMotion;
  const tq = moving ? Math.floor(t * 4) / 4 : 0;
  const sc = scale === 'XL' ? 'XL' : scale === 'S' && w <= 8 ? 'Ss' : scale === 'S' ? 'S' : 'M';
  // body frame: the body axis runs along the long side; a tall XL pane is painted transposed
  const tr = sc === 'XL' && h > w;
  const bw = tr ? h : w, bh = tr ? w : h;
  // skin units per logical pixel: M/S 1 (one cell column), desktop swatch zoomed out, XL a macro ~34 u across the body
  const k = sc === 'XL' ? 34 / bh : sc === 'Ss' ? 1.5 : 1;
  const ss = sc === 'XL' ? 2 : 3;                                // supersampling per axis
  const ox = ((seed >>> 8) & 255) * 1.37, oy = ((seed >>> 16) & 255) * 0.91;
  const ctx = { seed, tq, sc, visA: bw * k, visB: bh * k, aa: Math.max(0.12, k / ss), detail: sc === 'XL' ? 1 : 0.6,
    relief: sc === 'XL' ? 1 : 0.35, chroma: sc === 'XL' ? 0.32 : 1, grainAmp: sc === 'XL' ? 0.45 : 0, grid: { bw, bh, k, ss, ox, oy } };
  ctx.an = anatomy(ctx);
  ctx.Lbase = groundLightness(H);
  ctx.mirror = sc !== 'XL';                                       // chrome strips: the centre line is the body midline
  ctx.midB = ctx.an ? ctx.an.mid : ctx.visB / 2;
  const lay = layout(scale, w, h, state, session, degraded, opts);
  ctx.eyes = eyeList(state, ctx, tr ? 0 : lay.free * k);
  const key = `${sc}|${w}|${h}|${state}|${seed}|${H}`;
  let L0 = MEMO.get(key);
  if (!L0) {
    L0 = buildLayers(state, H, ctx);
    if (MEMO.size >= MEMO_MAX) MEMO.delete(MEMO.keys().next().value);
    MEMO.set(key, L0);
  }
  if (L0.px) return { pixels: L0.px.slice(), text: lay.text };      // static frame: identical for every t
  const eyes = ctx.eyes;
  const { ground, cov, covFull, tone, kmix, shade, spec } = L0;
  const cloud = working ? cloudField(ctx) : null;
  const px = new Uint8ClampedArray(w * h * 4);
  const hr = H == null ? 0 : (H * Math.PI) / 180;
  const SW = bw * ss, lab = [0, 0, 0], inv = 1 / (ss * ss);
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
    const p = y * bw + x, g = p * 3;
    const c = cloud ? cloud((x + 0.5) * k, ctx.mirror ? Math.min((y + 0.5) * k, 2 * ctx.midB - (y + 0.5) * k) : (y + 0.5) * k) : 0;
    let aL = 0, aA = 0, aB = 0;
    for (let sy = 0; sy < ss; sy++) for (let sx = 0; sx < ss; sx++) {
      const n = (y * ss + sy) * SW + x * ss + sx;
      lab[0] = ground[g] - 0.22 * c; lab[1] = ground[g + 1]; lab[2] = ground[g + 2];
      for (let ci = 2; ci >= 0; ci--) {
        let cv = cov[ci][n];
        if (c > 0) cv += (covFull[ci][n] - cv) * c;
        if (cv > 0) mixInto(lab, tone[ci], cv * kmix);
      }
      if (eyes.length || state === 'fault') overlay(state, eyes, lab, (x + (sx + 0.5) / ss) * k, (y + (sy + 0.5) / ss) * k, ctx);
      aL += lab[0]; aA += lab[1]; aB += lab[2];
    }
    const L = aL * inv * shade[p] + spec[p];
    const dc = 1 - 1.5 * spec[p];
    const dk = L < 0.32 ? Math.max(0, L / 0.32) : 1;             // deep shadow desaturates (and stays off the arc ends)
    const a = aA * inv * dc * dk, b = aB * inv * dc * dk;
    let rgb;
    if (working && H != null) {                                  // quantise onto the fixed identity palette
      const C = Math.sqrt(a * a + b * b);
      const li = Math.max(0, Math.min(WL - 1, Math.round((L - 0.2) / (0.95 - 0.2) * (WL - 1))));
      let ci = 0; for (let j = 1; j < WC.length; j++) if (Math.abs(WC[j] - C) < Math.abs(WC[ci] - C)) ci = j;
      const pal = L0.pal || (L0.pal = []), pi = li * WC.length + ci;
      rgb = pal[pi] || (pal[pi] = labRgb(0.2 + li * (0.95 - 0.2) / (WL - 1), WC[ci] * Math.cos(hr), WC[ci] * Math.sin(hr)));
    } else rgb = labRgb(L, a, b);
    if (H == null || state === 'unknown') { const gy = Math.round((rgb[0] + rgb[1] + rgb[2]) / 3); rgb = [gy, gy, gy]; }
    const i = (tr ? x * w + y : y * w + x) * 4;
    px[i] = rgb[0]; px[i + 1] = rgb[1]; px[i + 2] = rgb[2]; px[i + 3] = 255;
  }
  for (const pl of lay.plates) {
    for (let y = Math.max(0, pl.y0); y < Math.min(h, pl.y1); y++) for (let x = Math.max(0, pl.x0); x < Math.min(w, pl.x1); x++) {
      const i = (y * w + x) * 4; px[i] = pl.c[0]; px[i + 1] = pl.c[1]; px[i + 2] = pl.c[2]; px[i + 3] = 255;
    }
  }
  if (!moving) L0.px = px.slice();
  return { pixels: px, text: lay.text };
}
