// Direction C: "iridophore night". Pure ESM with no imports, timers or I/O (tools/p1/CONTRACT.md §2).
//
// A dark-mode skin, built in the animal's own layers:
//   dermis      deep identity hue (OKLCh) with slow, domain-warped tonal variation and relief lighting
//   sheen       iridophore filaments whose hue drifts within ±25° of the identity hue (clamped inside the
//               identity arc [110°, 340°)) and that lift the dermis where they run
//   sacs        chromatophores in three size classes on jittered lattices; each sac opens at its own
//               threshold, so every state's pattern EMERGES from an expansion field (no rectangles)
//   leucophores bright points clustered by a low-frequency density field, and the white fin line
// At XL the pane is a stretch of mantle seen from above: fins along both long sides with the pale
// marginal line, and dark night water beyond the ruffled fin edge.
// State = how the sacs and sheen organise:
//   idle      stipple: sacs retracted to points, scattered leucophore glints            (static)
//   working   passing cloud: a soft dark wave of expanded sacs drifting through bright sheen
//             (the ONLY animated state; quantised to 4 fps and <= 48 colours per frame)
//   review    mottle: irregular dark (expanded) and light (sheen) patches at two scales  (static)
//   needs-you zebra: wavy, tapering dark bands over leucophore white + soft-ringed amber eyespots
//   fault     deimatic: the skin blanches pale, sacs vanish, the margin flushes red
//   unknown   neutral grey hatch + "?" (no sheen, no sacs: no pattern claimed)

export const meta = {
  id: 'c-iridophore',
  name: 'Iridophore night',
  biology:
    'Sepia officinalis / Metasepia, dark-field: layered dermis (leucophore points, iridophore sheen, ' +
    'chromatophore sacs in 3 size classes, white fin line). idle = retracted-sac stipple; working = ' +
    'passing cloud (dark wave of expanded sacs); review = two-scale mottle; needs-you = wavy tapering ' +
    'zebra bands + soft-ringed ocelli; fault = deimatic blanch with flushed margin; unknown = no pattern.',
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
const lch = (L, C, h) => [L, C * Math.cos((h * Math.PI) / 180), C * Math.sin((h * Math.PI) / 180)];
const chromaCache = new Map();
function maxChroma(L, h) {
  const key = Math.round(L * 400) * 4000 + Math.round(h * 4);
  const hit = chromaCache.get(key);
  if (hit !== undefined) return hit;
  let lo = 0, hi = 0.4;
  for (let i = 0; i < 20; i++) {
    const c = (lo + hi) / 2;
    if (inGamut(oklabToLinear(...lch(L, c, h)))) lo = c; else hi = c;
  }
  chromaCache.set(key, lo);
  return lo;
}
const lchClip = (L, C, h) => lch(L, Math.min(C, maxChroma(L, h) * 0.97), h);
const mix = (p, q, k) => [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k, p[2] + (q[2] - p[2]) * k];
const lift = (c, dL) => [c[0] + dL, c[1], c[2]];
const clamp01 = v => (v < 0 ? 0 : v > 1 ? 1 : v);
const smoothstep = (a, b, v) => { const k = clamp01((v - a) / (b - a)); return k * k * (3 - 2 * k); };

// ---------- fixed (non-identity) colours ----------
const GREY = { ground: [0.25, 0, 0], line: [0.47, 0, 0] };
const WATER = [0.085, 0, 0];               // night water beyond the fin (XL only)
const AMBER = lch(0.81, 0.155, 74);        // eyespot iris (alarm only)
const AMBER_RIM = lch(0.62, 0.135, 58);    // eyespot outer iris (alarm only)
const PUPIL = [0.13, 0, 0];
const RED = lch(0.56, 0.19, 27);           // fault margin (alarm only)
const RED_SOFT = lch(0.70, 0.12, 24);

// Text plates. Fixed colours so authoredPairs() is the complete set (G2 contrast table).
const TEXT = {
  name: { fg: '#e8ecf1', bg: '#0c0f14' },
  input: { fg: '#1a1000', bg: '#f2a516' },
  error: { fg: '#ffffff', bg: '#b3121e' },
  unknown: { fg: '#0c0f14', bg: '#c9ccd1' },
};

// ---------- identity palette (memoised per hue) ----------
const ARC_LO = 110.5, ARC_HI = 339.5;
const sheenHue = (h, s) => Math.min(ARC_HI, Math.max(ARC_LO, h + 25 * (2 * s - 1)));
const palCache = new Map();
function identityPalette(h) {
  const hit = palCache.get(h);
  if (hit) return hit;
  // Dermis on the chrome scales: as dark as the hue allows while still carrying >= 0.118 chroma (blues and
  // violets L .40, the narrow-gamut teals rise to ~.6), so 20 hues 11.5° apart stay >= dE_OK .02 (G2).
  let L = 0.40;
  while (L < 0.64 && maxChroma(L, h) < 0.118) L += 0.01;
  const C = Math.min(0.15, maxChroma(L, h) * 0.97);
  const sheen = [], leuco = lchClip(0.95, 0.028, h);
  for (let k = 0; k <= 16; k++) sheen.push(lchClip(0.80, 0.09, sheenHue(h, k / 16)));
  const p = {
    h, L, C, base: lch(L, C, h), leuco,
    deep: lchClip(Math.max(0.15, L * 0.42), C * 0.55, h),
    sheenAt: s => sheen[Math.max(0, Math.min(16, Math.round(s * 16)))],
    // XL: the deep night dermis (identity is gated on the chrome scales, so XL may sit darker)
    xlBase: lchClip(Math.min(L, 0.47) - 0.05, C, h),
  };
  palCache.set(h, p);
  return p;
}

function neutralPalette(hue) {
  const h = hue === null ? 250 : hue, C = hue === null ? 0 : 0.04;
  const grey = lch(0.58, C * 0.5, h);
  return { h, L: 0.3, C, base: lch(0.3, C, h), xlBase: lch(0.3, C, h), leuco: lch(0.82, 0, h), deep: lch(0.16, C * 0.5, h),
    sheenAt: () => grey };
}

// ---------- deterministic hash / noise ----------
function hash2(x, y, seed) {
  let n = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(seed | 0, 1442695041)) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  n ^= n >>> 16;
  return (n >>> 0) / 4294967296;
}
function strSeed(s) {
  let n = 2166136261;
  for (let i = 0; i < s.length; i++) n = Math.imul(n ^ s.charCodeAt(i), 16777619);
  return (n >>> 0) % 1000003;
}
function vnoise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y);
  let fx = x - xi, fy = y - yi;
  fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
  const a = hash2(xi, yi, seed), b = hash2(xi + 1, yi, seed);
  const c = hash2(xi, yi + 1, seed), d = hash2(xi + 1, yi + 1, seed);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}
function fbm(x, y, seed, oct) {
  let s = 0, amp = 0.5, norm = 0;
  for (let i = 0; i < oct; i++) {
    s += amp * vnoise(x, y, seed + i * 131);
    norm += amp; amp *= 0.5; x = x * 2.03 + 17.1; y = y * 2.03 - 9.7;
  }
  return s / norm;
}
// Nearest jittered-lattice point: [distance, the point's own random value].
function nearest(x, y, cell, seed) {
  const gx = Math.floor(x / cell), gy = Math.floor(y / cell);
  let best = 1e9, rv = 0;
  for (let j = -1; j <= 1; j++) {
    for (let i = -1; i <= 1; i++) {
      const cx = gx + i, cy = gy + j;
      const px = (cx + 0.12 + 0.76 * hash2(cx, cy, seed)) * cell;
      const py = (cy + 0.12 + 0.76 * hash2(cx, cy, seed + 1)) * cell;
      const d = (x - px) * (x - px) + (y - py) * (y - py);
      if (d < best) { best = d; rv = hash2(cx, cy, seed + 2); }
    }
  }
  return [Math.sqrt(best), rv];
}
// A sac opens once the expansion e passes its own threshold rv; soft edge 0.5 px.
function sacCover(d, rv, e, rmax) {
  const open = clamp01((e - rv * 0.6) / 0.4);
  if (open <= 0) return 0;
  const r = rmax * (0.3 + 0.7 * open);
  return 1 - smoothstep(r - 0.5, r + 0.5, d);
}

function lru(map, key, value, cap) {
  if (map.size >= cap) map.delete(map.keys().next().value);
  map.set(key, value);
  return value;
}

// =====================================================================================================
// XL field: a stretch of mantle seen from above (fins along the long sides, night water beyond).
// =====================================================================================================
const xlCache = new Map();
function xlField(w, h, seed) {
  const key = `${w}|${h}|${seed}`;
  const hit = xlCache.get(key);
  if (hit) return hit;
  const n = w * h, tall = h >= w, S = Math.min(w, h);
  const f = S / 133; // feature scale: tuned on the 133-px-wide pane the desktop host paints
  const sc = 24 * f;
  const F = {
    f, S, tall,
    region: new Uint8Array(n), finT: new Float32Array(n), dome: new Float32Array(n),
    a: new Float32Array(n), b: new Float32Array(n), tone: new Float32Array(n), sheen: new Float32Array(n),
    hueS: new Float32Array(n), d0: new Float32Array(n), d1: new Float32Array(n), d2: new Float32Array(n),
    r0: new Float32Array(n), r1: new Float32Array(n), r2: new Float32Array(n), glint: new Float32Array(n),
    m1: new Float32Array(n), m2: new Float32Array(n), relief: new Float32Array(n), finLine: new Float32Array(n),
    big: new Float32Array(n), spec: new Float32Array(n), hueD: new Float32Array(n), chr: new Float32Array(n),
    gran: new Float32Array(n), leu: new Float32Array(n),
  };
  const height = new Float32Array(n);
  const finW = S * 0.13;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const A = (tall ? x : y) + 0.5, B = (tall ? y : x) + 0.5; // across / along the body
      const side = A < S / 2 ? 0 : 1, de = Math.min(A, S - A);
      // ruffled fin edge, then the fin, the pale marginal line, and the mantle
      const ruffle = S * 0.022 * (1.3 + Math.sin(B / (S * 0.05) + 6 * vnoise(B / (S * 0.3), side * 7, seed + 3)));
      const finEdge = finW + S * 0.03 * (vnoise(B / (S * 0.12), side * 5 + 2, seed + 5) - 0.5) * 2;
      F.region[i] = de < ruffle ? 0 : de < finEdge ? 1 : 2;
      F.finT[i] = clamp01((de - ruffle) / Math.max(1, finEdge - ruffle));
      // the pale fin line is a row of leucophore beads, not a ruled line
      const bead = smoothstep(0.1, 0.8, Math.cos(B / (1.3 * f) + 4 * vnoise(B / (S * 0.08), side, seed + 6)));
      F.finLine[i] = Math.max(0, 1 - Math.abs(de - finEdge) / (0.85 * Math.max(0.8, f))) * (0.35 + 0.65 * bead);
      F.dome[i] = clamp01((de - finEdge) / (S / 2 - finEdge));
      // domain warp
      const qx = fbm(A / sc, B / sc, seed + 11, 2), qy = fbm(A / sc + 5.2, B / sc + 1.3, seed + 23, 2);
      const WA = A + (qx - 0.5) * sc * 0.7, WB = B + (qy - 0.5) * sc * 0.7;
      F.a[i] = WA; F.b[i] = WB;
      F.tone[i] = fbm(WA / (sc * 1.5), WB / (sc * 1.5), seed + 41, 3);
      F.big[i] = fbm(A / (S * 0.5), B / (S * 0.5), seed + 43, 2);
      // iridophore filaments: ridged noise stretched across the body, their direction turning slowly
      const th = (fbm(A / (S * 0.8), B / (S * 0.8), seed + 51, 2) - 0.5) * 2.2;
      const ca = Math.cos(th), sa = Math.sin(th), RA = WA * ca - WB * sa, RB = WA * sa + WB * ca;
      const r = 1 - Math.abs(2 * fbm(RA / (sc * 1.4), RB / (sc * 0.3), seed + 57, 3) - 1);
      F.hueD[i] = fbm(WA / (sc * 1.8), WB / (sc * 1.8), seed + 61, 2);
      F.chr[i] = fbm(WA / (sc * 0.9), WB / (sc * 0.9), seed + 63, 2);
      F.sheen[i] = r * r * r;
      F.hueS[i] = fbm(WA / (sc * 2.4), WB / (sc * 2.4), seed + 71, 2);
      const s0 = nearest(WA, WB, 10 * f, seed + 101), s1 = nearest(WA, WB, 5.2 * f, seed + 211);
      const s2 = nearest(A, B, 2.9 * f, seed + 307);
      F.d0[i] = s0[0]; F.r0[i] = s0[1]; F.d1[i] = s1[0]; F.r1[i] = s1[1]; F.d2[i] = s2[0]; F.r2[i] = s2[1];
      const dens = smoothstep(0.35, 0.72, fbm(WA / (sc * 1.0), WB / (sc * 1.0), seed + 89, 2));
      const gp = F.region[i] === 1 ? 0.08 : 0.004 + 0.03 * dens;
      F.glint[i] = hash2(x, y, seed + 97) < gp ? 0.6 + 0.4 * hash2(x, y, seed + 98) : 0;
      // granular chromatophore bed: dense small soft dots of varying darkness (the skin's "grain")
      const gr = nearest(WA, WB, 2.7 * f, seed + 333);
      F.gran[i] = (1 - smoothstep(0.4 * f, 1.3 * f, gr[0])) * (0.2 + 0.8 * gr[1] * gr[1]);
      // leucophore white spots: small irregular blobs, sparse
      F.leu[i] = smoothstep(0.7, 0.8, fbm(WA / (sc * 0.16), WB / (sc * 0.16), seed + 341, 2)) *
        smoothstep(0.45, 0.65, fbm(WA / (sc * 0.9), WB / (sc * 0.9), seed + 343, 2));
      F.m1[i] = fbm(WA / (sc * 0.7), WB / (sc * 0.7), seed + 131, 3);
      F.m2[i] = fbm(WA / (sc * 0.26), WB / (sc * 0.26), seed + 151, 2);
      // skin height (in px): body dome + swells + raised iridophore ridges + papillae + the fin-root rim
      const pap = nearest(WA, WB, 7 * f, seed + 401);
      const pr = pap[0] / (1.8 * f);
      const ridge = smoothstep(0.25, 0.85, F.sheen[i]);
      const domeH = F.region[i] === 2 ? Math.sqrt(F.dome[i]) * S * 0.18 : F.finT[i] * S * 0.02;
      height[i] = domeH + f * (3 * F.big[i] + 1.5 * F.tone[i] + 0.7 * ridge + 0.9 * Math.exp(-pr * pr) * (0.4 + pap[1]) +
        0.6 * F.gran[i] + 1.2 * F.finLine[i]);
    }
  }
  // lighting: normals from the height field, light from the upper left, a soft specular for the wet sheen
  const lx = -0.45, ly = -0.55, lz = 0.7, ln = Math.hypot(lx, ly, lz);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const x0 = Math.max(0, x - 1), y0 = Math.max(0, y - 1), x1 = Math.min(w - 1, x + 1), y1 = Math.min(h - 1, y + 1);
      const gx = (height[y * w + x1] - height[y * w + x0]) / (x1 - x0), gy = (height[y1 * w + x] - height[y0 * w + x]) / (y1 - y0);
      const nn = Math.hypot(gx, gy, 1);
      const nx = -gx / nn, ny = -gy / nn, nz = 1 / nn;
      F.relief[i] = (nx * lx + ny * ly + nz * lz) / ln; // 1 = facing the light
      // Blinn half-vector with the viewer straight above
      const hx = lx / ln, hy = ly / ln, hz = lz / ln + 1, hn = Math.hypot(hx, hy, hz);
      const nh = Math.max(0, (nx * hx + ny * hy + nz * hz) / hn);
      F.spec[i] = nh ** 24;
    }
  }
  return lru(xlCache, key, F, 12);
}

function xlPainter(state, P, F, w, h, t, opts) {
  const f = F.f, tall = F.tall;
  const base = P.xlBase;
  let deep = lchClip(Math.max(0.12, base[0] * 0.42), P.C * 0.5, P.h);
  const leuco = P.leuco;
  const dermA = lchClip(base[0] - 0.02, P.C, sheenHue(P.h, 0.26)), dermB = lchClip(base[0] + 0.02, P.C, sheenHue(P.h, 0.74));
  let expand, sheenK = 0.5, glintK = 1, mantleExtra = null, toneK = 0.07, skin = base, granK = 0.4, leuK = 0.75;
  let grain = lchClip(Math.max(0.12, base[0] * 0.5), 0.035, P.h);
  if (state === 'idle') {
    expand = () => 0.1;
    sheenK = 0.55;
  } else if (state === 'working') {
    const tq = opts.reducedMotion ? 0 : Math.floor(t * 4) / 4;
    const along = tall ? h : w;
    const span = along * 0.6, width = along * 0.13, off = tq * (along / 22);
    expand = i => {
      const u = F.b[i] + 0.45 * F.a[i] + (F.tone[i] - 0.5) * along * 0.12;
      const p = ((((u - off) % span) + span) % span) / span - 0.5;
      const z = (p * span) / width;
      return 0.1 + 0.9 * Math.exp(-z * z * 1.8);
    };
    sheenK = 0.9; glintK = 0.4; granK = 0.25;
  } else if (state === 'review') {
    const m = i => 0.62 * F.m1[i] + 0.38 * F.m2[i];
    expand = i => 0.06 + 0.94 * smoothstep(0.5, 0.38, m(i));
    sheenK = 0.25; granK = 0.3; glintK = 0.4;
    mantleExtra = (i, c) => {
      const v = m(i);
      c = mix(c, deep, smoothstep(0.48, 0.38, v) * 0.55);
      return mix(c, P.sheenAt(F.hueS[i]), smoothstep(0.55, 0.66, v) * 0.6);
    };
  } else if (state === 'needs-you') {
    const period = 15 * f;
    const band = i => {
      const v = Math.cos((2 * Math.PI * (F.b[i] + 0.3 * F.a[i])) / period);
      const taper = 0.5 * (F.tone[i] - 0.5) + 0.35 * (F.dome[i] - 0.5); // bands thin toward the fins
      return smoothstep(0.0 + taper, 0.42 + taper, v);
    };
    expand = i => 0.05 + 0.95 * band(i);
    sheenK = 0.15; glintK = 0.3; leuK = 0;
    mantleExtra = (i, c) => mix(c, leuco, (1 - band(i)) * 0.72);
  } else if (state === 'unknown') {
    expand = () => 0.12;
    sheenK = 0.25; glintK = 0; leuK = 0.15; granK = 0.3;
  } else if (state === 'fault') {
    skin = lchClip(0.9, 0.028, P.h);
    deep = lchClip(0.74, 0.03, P.h);
    expand = () => 0.02;
    sheenK = 0.12; glintK = 0; toneK = 0.035; granK = 0.22; leuK = 0;
    grain = lchClip(0.7, 0.03, P.h);
  }
  const sacs = i => {
    const e = clamp01(expand(i) + 0.18 * (F.big[i] - 0.5));
    return Math.max(
      sacCover(F.d0[i], F.r0[i], e, 4.6 * f),
      0.9 * sacCover(F.d1[i], F.r1[i], e, 2.4 * f),
      (0.35 + 0.5 * F.r2[i]) * sacCover(F.d2[i], F.r2[i], Math.min(1, e + 0.22), 1.05 * f),
    );
  };
  return i => {
    const reg = F.region[i];
    if (reg === 0) return state === 'fault' ? mix(WATER, RED, 0.12) : WATER;
    const hd = F.hueD[i];
    const derm = state === 'fault' ? lift(skin, 0.03 * (hd - 0.5)) : hd < 0.5 ? mix(dermA, skin, hd * 2) : mix(skin, dermB, hd * 2 - 1);
    const ck = state === 'fault' ? 1 : 0.45 + 0.6 * F.chr[i];
    let c = lift([derm[0], derm[1] * ck, derm[2] * ck], toneK * (F.tone[i] - 0.5) * 2 + 0.05 * (F.big[i] - 0.5) * 2);
    const sh = smoothstep(0.35, 0.9, F.sheen[i]) * sheenK;
    if (sh > 0) c = mix(c, P.sheenAt(F.hueS[i]), sh);
    if (mantleExtra && reg === 2) c = mantleExtra(i, c);
    if (F.gran[i] > 0) c = mix(c, grain, F.gran[i] * granK);
    if (F.leu[i] > 0 && reg === 2) c = mix(c, leuco, F.leu[i] * leuK);
    const cov = sacs(i);
    if (cov > 0) c = mix(c, deep, cov * 0.8);
    if (reg === 1) {
      // fin: thinner, translucent toward the ruffled edge, dense fine leucophore speckle
      c = mix(WATER, lift(c, -0.04), 0.35 + 0.55 * smoothstep(0, 0.6, F.finT[i]));
      if (state === 'fault') c = mix(c, RED, 0.55 + 0.3 * (1 - F.finT[i]));
      if (F.glint[i] && state !== 'fault') c = mix(c, leuco, 0.55 * F.glint[i]);
    } else if (glintK && F.glint[i]) {
      c = mix(c, leuco, (state === 'working' ? 0.55 : 0.7) * glintK * F.glint[i]);
    }
    if (F.finLine[i] > 0) c = mix(c, state === 'fault' ? RED : leuco, F.finLine[i] * 0.35);
    return c;
  };
}
// Light the albedo: diffuse scales lightness (and chroma with it), the specular adds a wet sheen.
function lit(c, F, i, k) {
  const d = 1 + 0.45 * (F.relief[i] - 0.78) * k;
  const s = F.spec[i] * 0.04 * k;
  return [Math.min(0.99, c[0] * d + s), c[1] * Math.min(1.1, d), c[2] * Math.min(1.1, d)];
}
// needs-you ocelli (soft-ringed amber eyespots) and fault deimatic rings, on the mantle only
function xlSpots(state, F, w, h) {
  if (state !== 'needs-you') return null;
  const S = F.S, L = Math.max(w, h), tall = F.tall;
  const R = S * 0.09;
  const n = 2;
  const spots = [];
  for (let k = 0; k < n; k++) {
    const across = S * (k % 2 ? 0.64 : 0.36);
    const along = L * (k ? 0.68 : 0.3);
    spots.push(tall ? { x: across, y: along } : { x: along, y: across });
  }
  return (i, c) => {
    const x = (i % w) + 0.5, y = Math.floor(i / w) + 0.5;
    for (const s of spots) {
      const dx = x - s.x, dy = y - s.y, r0 = Math.hypot(dx, dy) / R;
      if (r0 > 1.6) continue;
      const wob = vnoise(dx / (R * 0.35) + s.x, dy / (R * 0.35) + s.y, 977) - 0.5;
      const r = r0 * (1 + 0.22 * wob);
      if (r > 1.25) continue;
      if (state === 'fault') {
        // deimatic eyespot: dark ring, pale centre, feathered
        if (r < 0.5) return c;
        if (r < 0.62) return mix(c, PUPIL, smoothstep(0.5, 0.62, r));
        if (r < 0.9) return PUPIL;
        return mix(PUPIL, c, smoothstep(0.9, 1.2, r));
      }
      if (r < 0.24) return mix(PUPIL, AMBER, smoothstep(0.18, 0.24, r));
      if (r < 0.62) return mix(AMBER, AMBER_RIM, smoothstep(0.4, 0.62, r));
      if (r < 0.92) return mix(AMBER_RIM, PUPIL, smoothstep(0.62, 0.78, r));
      return mix(PUPIL, c, smoothstep(0.92, 1.2, r));
    }
    return c;
  };
}

// =====================================================================================================
// Strips (TUI mantle, TUI pill, desktop chip): w cells × h px; pixels are tall (aspect = height/width).
// =====================================================================================================
const stripCache = new Map();
function stripField(w, h, aspect, seed) {
  const key = `${w}|${h}|${aspect}|${seed}`;
  const hit = stripCache.get(key);
  if (hit) return hit;
  const n = w * h;
  const F = { tone: new Float32Array(n), hueS: new Float32Array(n), warp: new Float32Array(n), m1: new Float32Array(n),
    m2: new Float32Array(n), glint: new Float32Array(n), pore: new Float32Array(n), Y: new Float32Array(n) };
  // glints on a jittered 1-D lattice (organic rhythm, never touching), pores (retracted sacs) between them
  const gl = new Map(), po = new Map();
  for (let k = 0; k * 5.5 < w + 6; k++) {
    const gx = Math.round(k * 5.5 + 3.2 * hash2(k, 1, seed)), gy = Math.floor(hash2(k, 2, seed) * h);
    gl.set(gy * w + gx, 0.65 + 0.35 * hash2(k, 3, seed));
    const px = Math.round(k * 5.5 + 2.75 + 2 * (hash2(k, 4, seed) - 0.5)), py = Math.floor(hash2(k, 5, seed) * h);
    if (px !== gx || py !== gy) po.set(py * w + px, 1);
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, Y = (y + 0.5) * aspect;
      F.Y[i] = Y;
      F.warp[i] = (fbm(x / 9, Y / 9, seed + 11, 2) - 0.5) * 4;
      F.tone[i] = fbm((x + F.warp[i]) / 16, Y / 10, seed + 41, 2);
      F.hueS[i] = fbm(x / 26, Y / 26, seed + 71, 2);
      F.m1[i] = fbm((x + F.warp[i]) / 8, Y / 4.5, seed + 131, 2);
      F.m2[i] = fbm((x - F.warp[i]) / 3.2, Y / 2.6, seed + 151, 2);
      F.glint[i] = gl.get(i) || 0;
      F.pore[i] = po.get(i) || 0;
    }
  }
  return lru(stripCache, key, F, 48);
}

function stripPainter(state, P, w, h, t, opts, seed) {
  const aspect = h <= 2 ? 2.2 : 1.1;
  const F = stripField(w, h, aspect, seed);
  const base = P.base, deep = P.deep, leuco = P.leuco;
  const midY = (h * aspect) / 2;
  const dermis = (i, k = 0.05) => lift(base, k * (F.tone[i] - 0.5) * 2);
  // a gentle iridophore ripple: quasi-periodic crests leaning with the tall cells
  const ripple = i => {
    const x = i % w;
    return 0.5 + 0.5 * Math.cos((2 * Math.PI * (x + F.warp[i] * 1.5 + (F.Y[i] - midY) * 0.8)) / 11);
  };
  if (state === 'idle') {
    return i => {
      let c = mix(dermis(i), P.sheenAt(F.hueS[i]), 0.12 * smoothstep(0.55, 1, ripple(i)));
      if (F.pore[i]) c = mix(c, deep, 0.6);
      if (F.glint[i]) c = mix(c, leuco, 0.92 * F.glint[i]);
      return c;
    };
  }
  if (state === 'working') {
    const tq = opts.reducedMotion ? 0 : Math.floor(t * 4) / 4;
    const span = Math.max(30, Math.min(64, w * 0.55)), width = Math.max(5, Math.min(12, w * 0.1));
    const off = tq * 4; // 4 px/s: one cell per frame
    return i => {
      const x = i % w;
      const u = x + F.warp[i] + (F.Y[i] - midY) * 1.1;
      const p = ((((u - off) % span) + span) % span) / span - 0.5;
      const z = (p * span) / width;
      const cloud = Math.exp(-z * z * 1.6);
      let c = mix(dermis(i, 0.04), P.sheenAt(F.hueS[i]), 0.55 * smoothstep(0.3, 1, ripple(i)) + 0.08);
      c = mix(c, deep, cloud * 0.92);
      if (F.glint[i] && cloud < 0.4) c = mix(c, leuco, 0.7);
      return c;
    };
  }
  if (state === 'review') {
    // dark patches on a jittered lattice (~13 cells) with ragged edges, small pale patches between them
    const blobs = [];
    for (let k = -1; k * 13 < w + 13; k++) {
      blobs.push({ x: k * 13 + 6 + 5 * (hash2(k, 9, seed) - 0.5), r: 3 + 3.2 * hash2(k, 10, seed), y: midY + (hash2(k, 11, seed) - 0.5) * aspect,
        lx: k * 13 + 12.5 + 2 * (hash2(k, 12, seed) - 0.5), lr: 1.2 + 1.3 * hash2(k, 13, seed) });
    }
    return i => {
      const x = i % w, Y = F.Y[i];
      let dk = 0, lt = 0;
      for (const b of blobs) {
        if (Math.abs(x - b.x) < b.r + 3) {
          const d = Math.hypot(x - b.x, (Y - b.y) * 0.8) / b.r + (F.m2[i] - 0.5) * 0.9;
          dk = Math.max(dk, 1 - smoothstep(0.75, 1.0, d));
        }
        if (Math.abs(x - b.lx) < b.lr + 2) {
          const d = Math.hypot(x - b.lx, (Y - midY) * 0.9) / b.lr + (F.m1[i] - 0.5) * 0.8;
          lt = Math.max(lt, 1 - smoothstep(0.7, 1.0, d));
        }
      }
      let c = dermis(i);
      c = mix(c, deep, dk * 0.88);
      return mix(c, P.sheenAt(F.hueS[i]), lt * 0.75);
    };
  }
  if (state === 'needs-you') {
    const nEyes = Math.max(1, Math.round(w / 30));
    const eyes = [];
    for (let k = 0; k < nEyes; k++) eyes.push(((k + 0.62) / nEyes) * (w - 1));
    const R = 2.5;
    return i => {
      const x = i % w;
      for (const ex of eyes) {
        const r = Math.hypot(x - ex, (F.Y[i] - midY) * 0.9) / R;
        if (r < 0.2) return PUPIL;
        if (r < 0.6) return AMBER;
        if (r < 0.85) return AMBER_RIM;
        if (r < 1.3) return PUPIL;
      }
      // bands: a steady rhythm whose phase and width drift slowly along the strip (wavy, tapering)
      const ph = x + 2.2 * Math.sin(x / 13 + seed) + (F.Y[i] - midY) * 0.45;
      const v = Math.cos((2 * Math.PI * ph) / 6.5);
      const thr = 0.25 * Math.sin(x / 21 + seed * 0.7);
      const dark = smoothstep(thr - 0.08, thr + 0.08, v);
      return mix(mix(leuco, P.sheenAt(F.hueS[i]), 0.3), deep, dark);
    };
  }
  if (state === 'fault') {
    const pale = lchClip(0.91, 0.028, P.h);
    return i => {
      const x = i % w, y = (i - x) / w;
      const d = Math.min(x, w - 1 - x);
      if (d < 2) return RED;
      if (d < 3) return RED_SOFT;
      if (h >= 3 && y === h - 1) return RED;
      let c = lift(pale, 0.02 * (F.tone[i] - 0.5) * 2 - 0.07 * smoothstep(0.6, 1, ripple(i)));
      if (F.pore[i]) c = lift(c, -0.06);
      return c;
    };
  }
  return () => base;
}

// =====================================================================================================
// Desktop swatch (4×2): a jewel of the same skin; working must move at 4×2.
// =====================================================================================================
function swatchPainter(state, P, w, h, t, opts, seed) {
  const H = P.h, base = P.base;
  const lo = lift(base, -0.035), hi = lift(base, 0.035);
  const grad = (x, y) => mix(hi, lo, (x + y * 1.5) / (w + 1.5));
  const glintX = Math.floor(hash2(1, 1, seed) * w), glintY = hash2(2, 2, seed) < 0.5 ? 0 : h - 1;
  if (state === 'idle') return (x, y) => (x === glintX && y === glintY ? P.leuco : grad(x, y));
  if (state === 'working') {
    const tq = opts.reducedMotion ? 0 : Math.floor(t * 4) / 4;
    const pos = ((tq * 4) % (w + 2)) - 1; // the dark wave steps one pixel per frame and wraps
    const sheen = P.sheenAt(0.8);
    return (x, y) => {
      const d = Math.abs(x + (y ? 0.5 : 0) - pos);
      if (d < 0.75) return P.deep;
      if (d < 1.6) return mix(P.deep, base, 0.55);
      return mix(grad(x, y), sheen, 0.3);
    };
  }
  if (state === 'review') return (x, y) => ((x + y) % 3 === 0 ? P.deep : x === 2 && y === 1 ? P.sheenAt(0.6) : grad(x, y));
  if (state === 'needs-you') return x => (x === 1 ? AMBER : x === 0 ? PUPIL : x === 3 ? P.deep : P.leuco);
  if (state === 'fault') return x => (x === 0 || x === w - 1 ? RED : lchClip(0.9, 0.03, H));
  return () => base;
}

// ---------- neutral hatch (unknown / degraded) ----------
function hatchPainter(scale, w, h, hue, seed) {
  const xl = scale === 'XL';
  const aspect = xl ? 1 : h <= 2 ? 2.2 : 1.1;
  const ground = hue === null ? GREY.ground : lchClip(0.28, 0.045, hue);
  const period = xl ? 7 : 5;
  return i => {
    const x = i % w, y = (i - x) / w;
    const wob = xl ? 1.6 * Math.sin(y / 9 + vnoise(x / 13, y / 13, seed) * 3) : 0;
    const d = (((x + y * aspect + wob) % period) + period) % period;
    if (d < 1) return GREY.line;
    if (xl && d < 2) return mix(GREY.line, ground, d - 1);
    return ground;
  };
}

// ---------- working palette: quantise to <= 48 colours (16 lightness × 3 hue steps) ----------
function quantiser(P) {
  // 48 lightness steps along one skin curve at the identity hue: chroma peaks at the dermis lightness and
  // falls toward the dark sacs and the pale leucophores. One curve = no salt-and-pepper between tiers.
  const LV = 48, lo = 0.07, hi = 0.97;
  const pal = [];
  for (let k = 0; k < LV; k++) {
    const L = lo + ((hi - lo) * k) / (LV - 1);
    const C = P.C * 0.8 * Math.max(0.15, 1 - Math.abs(L - P.L) / 0.5) * (L > 0.86 ? 0.4 : 1);
    pal.push(lchClip(L, C, P.h));
  }
  return c => {
    const k = Math.round(((c[0] - lo) / (hi - lo)) * (LV - 1));
    return pal[k < 0 ? 0 : k > LV - 1 ? LV - 1 : k];
  };
}

// ---------- labels ----------
function labels(scale, w, h, state, session) {
  if (scale === 'S' && w <= 8) return []; // D-R2-2: the desktop swatch carries no text
  const name = (session && session.name) || 'unbound';
  const alarm = session && session.alarm_text;
  const plates = [];
  if (state === 'needs-you' && alarm) plates.push({ str: alarm, ...TEXT.input, must: true });
  else if (state === 'fault' && alarm) plates.push({ str: alarm, ...TEXT.error, must: true });
  else if (state === 'unknown' || !session || session.hue_deg === null) plates.push({ str: '?', ...TEXT.unknown, must: true });
  plates.push({ str: name, ...TEXT.name });

  if (scale === 'XL') {
    let y = 18;
    const out = [];
    for (const p of plates) { out.push({ x: 30, y, str: ` ${p.str} `, fg: p.fg, bg: p.bg }); y += 26; }
    return out;
  }
  // Cell coordinates, row 0. Plates are padded by one space when room allows; the skin stays visible on
  // the rest of the row and (2-row mantles) the whole second row. The alarm/marker plate is always kept.
  const out = [];
  const gap = scale === 'S' ? 0 : 1;
  let x = scale === 'M' ? 1 : 0;
  for (const p of plates) {
    const padded = ` ${p.str} `;
    let str = x + padded.length <= w - gap ? padded : p.str;
    if (x + str.length > w) { if (!p.must) break; str = str.slice(0, Math.max(0, w - x)); }
    out.push({ x, y: 0, str, fg: p.fg, bg: p.bg });
    x += str.length + gap;
  }
  return out;
}

export function paint({ scale, w, h, state, session, t = 0, opts = {} }) {
  opts = opts || {};
  const hue = session && typeof session.hue_deg === 'number' ? session.hue_deg : null;
  const seed = strSeed(String((session && (session.lineage_id || session.name)) || 'unbound'));
  const n = w * h;
  let fn;
  if ((state === 'unknown' || hue === null) && scale === 'XL') {
    // the same body, drained of colour (no identity claimed; a stale-but-known session keeps a faint
    // tint so "who" stays findable), with the neutral hatch engraved over it
    const P = neutralPalette(state === 'unknown' ? hue : null);
    const F = xlField(w, h, seed);
    const body = xlPainter('unknown', P, F, w, h, t, opts);
    const hatch = hatchPainter(scale, w, h, null, seed);
    fn = i => (F.region[i] === 0 ? body(i) : mix(lit(body(i), F, i, 1), hatch(i), hatch(i) === GREY.line ? 0.5 : 0));
  } else if (state === 'unknown' || hue === null) {
    fn = hatchPainter(scale, w, h, hue, seed);
  } else {
    const P = identityPalette(hue);
    let skin;
    if (scale === 'S' && w <= 8) {
      const sp = swatchPainter(state, P, w, h, t, opts, seed);
      skin = i => sp(i % w, Math.floor(i / w));
    } else if (scale === 'XL') {
      const F = xlField(w, h, seed);
      const body = xlPainter(state, P, F, w, h, t, opts);
      const spots = xlSpots(state, F, w, h);
      const lk = 1;
      skin = i => {
        if (F.region[i] === 0) return body(i);
        const c = spots && F.region[i] === 2 ? spots(i, body(i)) : body(i);
        return lit(c, F, i, lk);
      };
    } else {
      skin = stripPainter(state, P, w, h, t, opts, seed);
    }
    const q = state === 'working' ? quantiser(P) : null;
    fn = q ? i => q(skin(i)) : skin;
  }
  const pixels = new Uint8ClampedArray(n * 4);
  for (let i = 0; i < n; i++) {
    const c = fn(i);
    const v = oklabToLinear(c[0], c[1], c[2]);
    for (let k = 0; k < 3; k++) pixels[i * 4 + k] = Math.round(255 * lin2srgb(Math.min(1, Math.max(0, v[k]))));
    pixels[i * 4 + 3] = 255;
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
