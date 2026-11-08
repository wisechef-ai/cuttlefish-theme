// HTML builders for the golden renders (dev-only). Pure strings; render.mjs screenshots them with headless Chromium.
import { renderField, toSvg, allocate, patternOf, DEFAULT_SETTINGS } from '../../desktop/src/domain/index.ts'
import { BOX, GLYPHS, STATES, HUES, STRIP_K, RIM_H, glyphSvg, rimSvg, palette, fieldPost } from './model.mjs'

/** The Desktop grounds the language is measured on. `chat` is what the plugin reads; row/sel are the sidebar's. */
export const GROUNDS = {
  light: { chat: '#fefefe', side: '#f6f8fa', sel: '#d8e1f0', text: '#1c2230', mute: '#6b7384', card: '#ffffff', edge: '#d9dde6', bar: '#f6f8fa' },
  dark: { chat: '#141416', side: '#17181c', sel: '#2a3142', text: '#e6e8ee', mute: '#8a90a0', card: '#1b1c20', edge: '#2c2f38', bar: '#17181c' },
  nord: { chat: '#2e3440', side: '#2e3440', sel: '#434c5e', text: '#e5e9f0', mute: '#9aa3b5', card: '#353c4a', edge: '#434c5e', bar: '#2b303b' },
}
export const LABELS = { resting: '', working: 'working', needs_you: 'needs you', error: 'error', finished_unseen: 'done' }
const TITLES = {
  resting: 'quiet note', working: 'long task', needs_you: 'risky command', error: 'broken request', finished_unseen: 'slow answer',
}
const FONT = `font-family:Inter,"Noto Sans","DejaVu Sans",system-ui,sans-serif`

export const css = `*{box-sizing:border-box;margin:0;padding:0}body{${FONT};-webkit-font-smoothing:antialiased}svg{display:block}`

/** One sidebar row: [core dot][glyph][title][age]. */
export function rowHtml(g, state, hue, selected, w = 240, title = TITLES[state]) {
  const G = GROUNDS[g]
  return `<div style="width:${w}px;height:27px;display:flex;align-items:center;gap:8px;padding:0 10px;background:${selected ? G.sel : G.side};color:${G.text};font-size:13px;border-radius:6px">
    <span style="width:6px;height:6px;border-radius:3px;background:${G.mute};opacity:.5;flex:none"></span>
    <span style="flex:none;width:${BOX.w}px;height:${BOX.h}px">${glyphSvg(state, hue, G.chat)}</span>
    <span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${title}</span><span style="font-size:11px;color:${G.mute}">1m</span></div>`
}

export function stripHtml(g, state, hue) {
  const G = GROUNDS[g], label = LABELS[state] || 'resting'
  return `<div data-cf-strip style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;line-height:1;flex-shrink:0;font-size:12px;font-weight:600;color:${G.text}">
    <span style="display:block;width:${BOX.w * STRIP_K}px;height:${BOX.h * STRIP_K}px">${glyphSvg(state, hue, G.chat, STRIP_K)}</span>${label}</div>`
}

export function rimHtml(g, state, hue, w) { return rimSvg(state, hue, GROUNDS[g].chat, w) }

/** The field layer: the domain's own renderField (baseline). */
export function fieldUrl(g, state, hue, w, h, seed = 'cf-demo', over = {}) {
  const dots = renderField({ seed, width: w, height: h, hueDeg: hue, ground: GROUNDS[g].chat, pattern: patternOf(DEFAULT_SETTINGS, state),
    intensity: 1, motion: 'still', reducedMotion: false, tMs: 4200, sinceChangeMs: 99999, ...over })
  const post = over.post ? over.post(dots, w, h) : dots
  return `url('data:image/svg+xml,${encodeURIComponent(toSvg(post, w, h))}')`
}

const PARA = [
  'I looked through the repository and found three places where the retry loop swallows the original error. The first is in the client wrapper,',
  'where the exception is replaced by a generic message before it ever reaches the caller; the other two are in the scheduler.',
]

/** A whole 1280×800 Desktop: sidebar with the five states, chat field of the focused state, composer rim, status strip. */
export function appHtml(g, focus, opts = {}) {
  const G = GROUNDS[g], W = 1280, H = 800, SB = 240, CW = W - SB, CH = H - 34 - 22
  const hue = HUES[STATES.indexOf(focus)]
  const rows = STATES.map((s, i) => rowHtml(g, s, HUES[i], s === focus, SB - 16)).join('')
  const field = fieldUrl(g, focus, hue, CW, CH, 'cf-' + focus, { post: (d, w, h) => fieldPost(d, w, h, G.chat, hue) })
  const card = focus === 'needs_you' ? `<div style="margin:14px 0 0 24px;width:560px;border:1px solid ${G.edge};background:${G.card};border-radius:8px;padding:12px;font-size:12px">
      <div style="color:${G.mute}">Command</div><div style="font-family:monospace;margin:8px 0">rm -rf /tmp/cuttlefish-demo-target</div>
      <div style="text-align:right;color:${G.mute}">Reject &nbsp; <span style="border:1px solid ${G.edge};padding:3px 8px;border-radius:5px">Always allow…</span> <span style="background:#1d5cf0;color:#fff;padding:4px 10px;border-radius:5px">Run</span></div></div>` : ''
  const err = focus === 'error' ? `<div style="margin:14px 0 0 24px;width:560px;border:1px solid #d9a6ad;background:${g === 'light' ? '#fdf1f3' : '#3a2227'};color:${g === 'light' ? '#8a2b3a' : '#f0b9c1'};border-radius:8px;padding:12px;font-size:13px">Request failed (HTTP 400). The model call was rejected.</div>` : ''
  return `<html><head><style>${css}</style></head><body style="width:${W}px;height:${H}px;background:${G.side};color:${G.text};position:relative;overflow:hidden">
  <div style="position:absolute;left:0;top:0;width:${SB}px;height:${H}px;padding:60px 8px 0;background:${G.side}">
    <div style="font-size:11px;letter-spacing:.12em;color:${G.mute};margin:0 10px 10px">SESSIONS</div>${rows}</div>
  <div style="position:absolute;left:${SB}px;top:0;width:${CW}px;height:34px;background:${G.side};border-bottom:1px solid ${G.edge};font-size:11px;padding:11px 14px;letter-spacing:.04em">${TITLES[focus].toUpperCase()}</div>
  <div style="position:absolute;left:${SB}px;top:34px;width:${CW}px;height:${CH}px;background:${field} 0 0/${CW}px ${CH}px no-repeat,${G.chat};">
    <div style="padding:14px 24px;font-size:14px;line-height:1.55;max-width:760px"><div style="border:1px solid ${G.edge};background:${G.card};padding:10px 12px;border-radius:6px;margin-bottom:12px">${TITLES[focus]}</div>
    ${PARA.map(p => `<p style="margin-bottom:10px">${p}</p>`).join('')}</div>${card}${err}
    <div style="position:absolute;left:12px;right:12px;bottom:10px"><div style="overflow:hidden;border-radius:6px 6px 0 0">${rimHtml(g, focus, hue, CW - 24)}</div>
      <div style="height:46px;border:1px solid ${G.edge};border-top:0;background:${G.card};border-radius:0 0 10px 10px;padding:13px 14px;color:${G.mute};font-size:14px">What should we tackle?</div></div></div>
  <div style="position:absolute;left:${SB}px;top:${H - 22}px;width:${CW}px;height:22px;background:${G.bar};border-top:1px solid ${G.edge};display:flex;justify-content:flex-end;align-items:center;gap:18px;padding:0 14px;font-size:11px;color:${G.mute}"><span>Smart</span><span>v0.22.7</span>${stripHtml(g, focus, hue)}</div>
  </body></html>`
}
