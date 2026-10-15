// Direction D: "dots" (cf2909 P1, Adam 2026-10-15: "simply a set of coloured dots without any
// sophisticated background").
//
// The whole look is chromatophores and nothing else: a lattice of coloured dots on one plain, flat,
// terminal-dark ground. No mantle silhouette, no shading layer, no texture under the dots.
//   hue     = identity (the session's OKLCh hue; never amber/red; grey only for unknown/degraded)
//   pattern = state, expressed only by which dots are expanded, contracted or blanched:
//     idle       uniform stipple: every dot open, a few closed at random (static)
//     working    passing cloud: a band of closed dots drifts across the field (the ONLY animated state)
//     review     mottle: dots open/close in soft blotches
//     needs-you  zebra: alternating open/closed dot bands + two amber eyespots + literal `INPUT 4m`
//     fault      deimatic blanch: every dot opens pale, red dots on the margin + literal `ERROR 2m`
//     unknown    sparse grey dots on a diagonal, no identity hue + `?` (degraded: label `unbound`)
// XL (desktop field) draws round anti-aliased dots on a hex lattice at low internal resolution; M and S
// (mantle, chip, pill, swatch) are the same grammar with one dot per logical pixel.
// Contract: tools/p1/CONTRACT.md §2 (pure ESM, no imports, no timers, no I/O). Tokens: packages/core/tokens.json.

export const meta = {
  id: 'd-dots',
  name: 'Dots (chromatophores on a plain ground)',
  biology: 'Sepia chromatophore states only: uniform stipple, passing cloud, mottle, zebra + eyespots, deimatic blanch',
  maxColorsWorking: 48,
  fps: 4,
};

const clamp01 = v => Math.min(1, Math.max(0, v));

// OKLCh → sRGB 0..255 (Ottosson's OKLab matrices), clipped to gamut.
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ].map(c => {
    const v = clamp01(c);
    return Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
  });
}

// ---- tokens (mirrored in packages/core/tokens.json) ----
export const TOKENS = {
  ground: [14, 15, 19],            // the one plain background
  dot: { L: [0.58, 0.66, 0.74], C: 0.135 },   // three lightness steps of the identity hue
  blanch: { L: 0.9, C: 0.035 },
  grey: { L: 0.6, C: 0 },
  amber: [255, 176, 0],
  red: [214, 40, 57],
  ink: '#f2f2f2', plate: '#14151a',
  alarmBg: { 'needs-you': '#ffb000', fault: '#b00020' },
  alarmFg: { 'needs-you': '#000000', fault: '#ffffff' },
  xlPitch: 7,                      // XL dot pitch in internal px (pane is upscaled ×4 with smoothing)
};

// Deterministic hash → [0, 1).
function hash(i, j, k = 0) {
  let n = (i * 374761393 + j * 668265263 + k * 2147483647) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}

// Smooth value noise for the mottle blotches.
function vnoise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed), c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

// One dot's look: { open: 0..1 (how expanded), tone: rgb }.  (c, r) are dot coords, (cols, rows) the lattice size.
function dotLook(c, r, cols, rows, state, step, colors, seed, scaleKind) {
  const j = hash(c, r, seed);
  const shade = colors.dots[Math.floor(j * 3) % 3];
  switch (state) {
    case 'idle':
      return { open: j < 0.18 ? 0 : 1, tone: shade };
    case 'working': {
      // A band of closed dots drifts left→right one dot per frame (≤ 4 fps): the passing cloud.
      // Narrow strips (pill, chip) get a short period so the cloud is always visible beside the label.
      const narrow = scaleKind === 'M' && cols <= 30;
      const period = scaleKind === 'S' ? Math.max(3, cols) : narrow ? 6 : scaleKind === 'M' ? 16 : 14;
      const half = scaleKind === 'S' ? 0 : narrow ? 1 : scaleKind === 'M' ? 2 : 3;
      const pos = ((c + Math.floor(r * 0.5) - step) % period + period) % period;
      const d = Math.min(pos, period - pos);
      if (d <= half) return { open: d === half && half > 0 ? 0.5 : 0, tone: shade };
      return { open: j < 0.1 ? 0 : 1, tone: shade };
    }
    case 'review': {
      const k = scaleKind === 'XL' ? 5 : 3;
      const n = vnoise(c / k, r / (scaleKind === 'XL' ? k : 1.2), seed + 7);
      if (n < 0.38) return { open: 0, tone: shade };
      return { open: n < 0.5 ? 0.5 : 1, tone: n > 0.66 ? colors.dots[2] : colors.dots[0] };
    }
    case 'needs-you': {
      const band = scaleKind === 'XL' ? Math.floor((c + (r & 1) * 0.5 + r * 0.5) / 2) : Math.floor(c / 2);
      return band % 2 === 0 ? { open: 1, tone: colors.dots[2] } : { open: 0, tone: shade };
    }
    case 'fault': {
      const edge = scaleKind === 'XL' ? 2 : 1;
      const onEdge = c < edge || c >= cols - edge || (scaleKind === 'XL' && (r < edge || r >= rows - edge));
      if (onEdge) return { open: 1, tone: TOKENS.red };
      return { open: j < 0.06 ? 0.5 : 1, tone: colors.blanch };
    }
    default: // unknown / degraded: sparse grey dots on a diagonal, no identity claim
      return { open: (c + r) % 3 === 0 ? 1 : 0, tone: colors.grey };
  }
}

function eyespots(scaleKind, w, h) {
  if (scaleKind === 'XL') {
    const r = Math.max(4, Math.min(w, h) * 0.09);
    return [{ x: w * 0.3, y: h * 0.5, r }, { x: w * 0.7, y: h * 0.5, r }];
  }
  if (w <= 8) return [{ x: w - 1, y: 0, r: 0 }];
  return [{ x: Math.floor(w * 0.35), y: Math.floor((h - 1) / 2), r: 0 }, { x: Math.floor(w * 0.65), y: Math.floor((h - 1) / 2), r: 0 }];
}

function put(px, i, c) { px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255; }
const mix = (a, b, k) => [0, 1, 2].map(n => Math.round(a[n] + (b[n] - a[n]) * k));

export function paint({ scale, w, h, state, session, t, opts }) {
  const degraded = session == null || session.hue_deg == null;
  const look = degraded ? 'unknown' : state;
  const hue = degraded ? 0 : session.hue_deg;
  const colors = {
    dots: TOKENS.dot.L.map(L => oklch(L, TOKENS.dot.C, hue)),
    blanch: oklch(TOKENS.blanch.L, TOKENS.blanch.C, hue),
    grey: oklch(TOKENS.grey.L, TOKENS.grey.C, 0),
  };
  const moving = look === 'working' && !(opts && opts.reducedMotion);
  const step = moving ? Math.floor((t || 0) * 4) : 0;   // one dot per 0.25 s: ≤ 4 fps
  const seed = degraded ? 1 : Math.round(hue * 10);
  const G = TOKENS.ground;
  const px = new Uint8ClampedArray(w * h * 4);
  const kind = scale === 'XL' ? 'XL' : (w <= 8 ? 'S' : 'M');

  if (scale === 'XL') {
    const P = TOKENS.xlPitch, RP = P * 0.866, R = P * 0.36;
    const rows = Math.ceil(h / RP) + 1, cols = Math.ceil(w / P) + 1;
    const spots = look === 'needs-you' ? eyespots('XL', w, h) : [];
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
            const cov = Math.round(clamp01(rad - dist + 0.5) * 3) / 3;   // 4 coverage levels: a soft, few-colour edge
            if (cov > best) { best = cov; col = mix(G, d.tone, cov); }
          }
        }
        for (const s of spots) {
          const d = Math.hypot(x - s.x, y - s.y);
          if (d < s.r * 0.35) col = G;                           // pupil
          else if (d < s.r) col = TOKENS.amber;
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
        if (spots.some(s => s.x === x && s.y === y)) col = TOKENS.amber;
        put(px, (y * w + x) * 4, col);
      }
    }
  }

  const text = [];
  const name = degraded ? 'unbound' : session.name;
  const alarm = look === 'unknown' ? '?' : (session && session.alarm_text) || null;
  const fg = TOKENS.alarmFg[look] ?? TOKENS.ink, bg = TOKENS.alarmBg[look] ?? TOKENS.plate;
  if (scale === 'XL') {
    text.push({ x: 16, y: 16, str: name, fg: TOKENS.ink, bg: TOKENS.plate });
    if (alarm) text.push({ x: 16, y: 48, str: alarm, fg, bg });
  } else if (w > 8) {
    const label = ` ${name} `.slice(0, w);
    const s = alarm ? ` ${alarm} ` : '';
    if (!alarm) text.push({ x: 0, y: 0, str: label, fg: TOKENS.ink, bg: TOKENS.plate });
    else if (label.length + s.length <= w) {
      text.push({ x: 0, y: 0, str: label, fg: TOKENS.ink, bg: TOKENS.plate });
      text.push({ x: w - s.length, y: 0, str: s, fg, bg });
    } else {
      text.push({ x: 0, y: 0, str: s.slice(0, w), fg, bg });   // too narrow for both: the alarm wins
    }
  } // desktop S swatch (w ≤ 8): no text — the sidebar row carries the name (CONTRACT §2, §13.4 #7)
  return { pixels: px, text };
}

export function authoredPairs() {
  return [
    { fg: TOKENS.ink, bg: TOKENS.plate, where: 'name label (all scales), unknown ? chip' },
    { fg: TOKENS.alarmFg['needs-you'], bg: TOKENS.alarmBg['needs-you'], where: 'INPUT alarm chip' },
    { fg: TOKENS.alarmFg.fault, bg: TOKENS.alarmBg.fault, where: 'ERROR alarm chip' },
  ];
}
