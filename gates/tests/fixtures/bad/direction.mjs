// THROWAWAY test direction for the gate harness (BAD fixture): every defect planted on purpose. All six states are one flat fill; identity is
// grey for sessions 0-9 and RED for the rest; text sits at about 2:1; review changes with t. G2 must name each one.
export const meta = { id: 'bad', name: 'Gate fixture (bad)', biology: 'none: synthetic', maxColorsWorking: 48, fps: 4 };

const lin = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180, a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
  return rgb.map(v => Math.round(Math.min(1, Math.max(0, lin(Math.min(1, Math.max(0, v))))) * 255));
}
const TEXT_FG = '#767676', TEXT_BG = '#4a4a4a';  // 1.94:1 on purpose

function fill(session, state, t) {
  if (session.hue_deg === null) return [110, 110, 110];
  const L = (state === 'review' || state === 'working') ? 0.45 + 0.2 * t : 0.55;  // review must NOT change with t
  return session.idx < 10 ? oklch(L, 0.004, session.hue_deg) : oklch(L, 0.15, 25);               // greys, then a red identity
}

export function paint({ scale, w, h, state, session, t }) {
  const c = fill(session, state, t), pixels = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    pixels[i] = c[0]; pixels[i + 1] = c[1]; pixels[i + 2] = c[2]; pixels[i + 3] = 255;
  }
  const text = [];
  const cell = scale !== 'XL';
  if (cell) {
    const name = state === 'unknown' ? (session.hue_deg === null ? 'unbound' : session.name) : session.name;
    text.push({ x: 1, y: scale === 'M' ? 0 : (h >= 4 ? 1 : 0), str: name.slice(0, 8), fg: TEXT_FG, bg: TEXT_BG });
    if (scale === 'M' && h >= 4) text.push({ x: 1, y: 1, str: session.alarm_text ?? (state === 'unknown' ? '?' : ''), fg: TEXT_FG, bg: TEXT_BG });
    else if (scale === 'S' && w <= 14 && session.alarm_text) text[0].str = session.alarm_text;
  } else if (session.alarm_text) text.push({ x: 8, y: 8, str: session.alarm_text, fg: TEXT_FG, bg: TEXT_BG });
  return { pixels, text: text.filter(x => x.str) };
}

export function authoredPairs() {
  return [{ fg: TEXT_FG, bg: TEXT_BG, where: 'name + alarm text' }];
}
