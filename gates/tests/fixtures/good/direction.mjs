// THROWAWAY test direction for the gate harness (GOOD fixture): distinct pattern per state, identity carried by the
// majority colour, high-contrast text. Not a design; it only has to be what a passing direction looks like to G2/G5.
export const meta = { id: 'good', name: 'Gate fixture (good)', biology: 'none: synthetic', maxColorsWorking: 48, fps: 4 };

const lin = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
function oklch(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180, a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
  return rgb.map(v => Math.round(Math.min(1, Math.max(0, lin(Math.min(1, Math.max(0, v))))) * 255));
}
const hash = (x, y) => ((x * 73856093) ^ (y * 19349663)) >>> 0;
const TEXT_FG = '#f5f5f5', TEXT_BG = '#14141c';

function colours(session) {
  if (session.hue_deg === null) return { base: [96, 96, 96], light: [150, 150, 150], dark: [50, 50, 50] };
  const h = session.hue_deg;
  return { base: oklch(0.55, 0.15, h), light: oklch(0.78, 0.12, h), dark: oklch(0.32, 0.10, h) };
}

function pick(state, x, y, t, w) {
  switch (state) {
    case 'idle': return hash(x, y) % 6 === 0 ? 'light' : 'base';
    case 'working': { const c = (Math.floor(t * 4) * 3) % w; return Math.abs(x - c) < Math.max(2, w / 10) ? 'dark' : 'base'; }
    case 'review': return (Math.floor(x / 3) + Math.floor(y / 2)) % 3 === 0 ? 'dark' : hash(Math.floor(x / 3), Math.floor(y / 2)) % 2 ? 'base' : 'light';
    case 'needs-you': return Math.floor(x / 2) % 2 ? 'dark' : 'light';
    case 'fault': return (x + y) % 2 ? 'dark' : 'light';
    default: return (x + y) % 4 === 0 ? 'dark' : 'base';
  }
}

export function paint({ scale, w, h, state, session, t }) {
  const col = colours(session), pixels = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const c = col[pick(state, x, y, t, w)], i = (y * w + x) * 4;
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
