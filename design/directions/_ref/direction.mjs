// REFERENCE DIRECTION — harness proof only. NOT a design candidate, never gate-scored as one.
//
// cf2909 P1-H (host-harness lane) wrote this to prove the capture pipeline end to end: the real TUI widget,
// the real desktop plugin and capture_matrix.py all render it, and the PNGs are inspected by eye. It is
// deliberately plain so that a broken host is obvious:
//   hue      = the session's identity hue (flat OKLCh fill, L 0.55 / C 0.12), grey for the degraded entry
//   pattern  = dot density per state (idle sparse … fault dense), dots are light/dark structure, not shading
//   alarms   = literal text (`INPUT 4m`, `ERROR 2m`) on a solid amber / red chip; unknown carries `?`
//   working  = the dot lattice drifts 1 px per 0.25 s (a coarse ≤ 4 fps step, ≤ 48 colours)
// Contract: tools/p1/CONTRACT.md §2 (pure ESM, no imports, no timers, no I/O).

export const meta = {
  id: '_ref',
  name: 'Reference (harness proof, not a candidate)',
  biology: 'none: flat hue + dot density per state; a harness reference, not a body pattern',
  maxColorsWorking: 48,
  fps: 4,
};

const clamp01 = v => Math.min(1, Math.max(0, v));

// OKLCh → sRGB 0..255 (Björn Ottosson's OKLab matrices), clipped to gamut.
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
  return lin.map(c => {
    const v = clamp01(c);
    return Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
  });
}

// Dot lattice period per state: smaller = denser. Structure, so it survives the 256 rung and CVD sims.
const PERIOD = { idle: 8, working: 5, review: 4, 'needs-you': 3, fault: 2, unknown: 0 };

const INK = '#ffffff';
const LABEL_BG = '#141418';
const ALARM_BG = { 'needs-you': '#ffb000', fault: '#b00020' };
const ALARM_FG = { 'needs-you': '#000000', fault: '#ffffff' };

export function paint({ scale, w, h, state, session, t, opts }) {
  const degraded = session == null || session.hue_deg == null;
  const base = degraded ? [92, 92, 100] : oklch(0.55, 0.12, session.hue_deg);
  const lite = degraded ? [150, 150, 158] : oklch(0.78, 0.09, session.hue_deg);
  const alarm = state === 'needs-you' ? [255, 176, 0] : state === 'fault' ? [176, 0, 32] : null;
  const dot = alarm ?? lite;
  const period = degraded ? 0 : PERIOD[state] ?? 0;
  const moving = state === 'working' && !(opts && opts.reducedMotion);
  const shift = moving ? Math.floor((t || 0) * 4) : 0; // 1 px per 0.25 s, quantised: ≤ 4 fps
  // XL is 1 logical px per CSS px: scale the lattice so a dot reads at desktop size.
  const k = scale === 'XL' ? 6 : 1;

  const pixels = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let c = base;
      const gx = Math.floor(x / k), gy = Math.floor(y / k);
      if (period === 0) {
        // unknown / degraded: a neutral diagonal hatch, no identity claim.
        if ((gx + gy) % 4 === 0) c = lite;
      } else if ((gx + shift) % period === 0 && gy % 2 === 0) {
        c = dot;
      }
      const i = (y * w + x) * 4;
      pixels[i] = c[0]; pixels[i + 1] = c[1]; pixels[i + 2] = c[2]; pixels[i + 3] = 255;
    }
  }

  const text = [];
  const name = degraded ? 'unbound' : session.name;
  const alarmText = state === 'unknown' ? '?' : session && session.alarm_text;
  if (scale === 'XL') {
    text.push({ x: 16, y: 16, str: name, fg: INK, bg: LABEL_BG });
    if (alarmText) text.push({ x: 16, y: 48, str: alarmText, fg: ALARM_FG[state] ?? INK, bg: ALARM_BG[state] ?? LABEL_BG });
  } else {
    // M / S: cell coordinates. Name at the left, alarm at the right of row 0.
    const label = ` ${name} `.slice(0, Math.max(0, w));
    text.push({ x: 0, y: 0, str: label, fg: INK, bg: LABEL_BG });
    if (alarmText) {
      const s = ` ${alarmText} `;
      const x = Math.max(label.length, w - s.length);
      if (x + s.length <= w) text.push({ x, y: 0, str: s, fg: ALARM_FG[state] ?? INK, bg: ALARM_BG[state] ?? LABEL_BG });
    }
  }
  return { pixels, text };
}

export function authoredPairs() {
  return [
    { fg: INK, bg: LABEL_BG, where: 'name label (all scales)' },
    { fg: ALARM_FG['needs-you'], bg: ALARM_BG['needs-you'], where: 'INPUT alarm chip' },
    { fg: ALARM_FG.fault, bg: ALARM_BG.fault, where: 'ERROR alarm chip' },
    { fg: INK, bg: LABEL_BG, where: 'unknown ? chip' },
  ];
}

