// HTML builders for the golden renders (dev-only). Pure strings; render.mjs screenshots them with headless Chromium.
import { renderField, toSvg, allocate, patternOf, DEFAULT_SETTINGS } from '../../desktop/src/domain/index.ts'
import { BOX, GLYPHS, STATES, HUES, STRIP_K, RIM_H, glyphSvg, rimSvg, palette } from './model.mjs'

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

const TEXT = {
  resting: [
    ['user', 'Why does the retry loop hide the original error?'],
    ['bot', 'I looked through the repository and found three places where the retry loop swallows the original exception. The first is in the client wrapper, where the error is replaced by a generic message before it ever reaches the caller. The other two are in the scheduler: both catch the exception, log a single line without the stack, and then retry with the same arguments, so a permanent failure looks exactly like a transient one.'],
    ['bot', 'Here is what I would change, in order: keep the original exception as the cause, stop retrying on 4xx responses, and surface the last error after the final attempt. Each of these is a small, separate patch, and none of them changes the public API of the client.'],
  ],
  working: [
    ['user', 'Find every place that retries a request and list them.'],
    ['tool', 'grep -rn "retry" src/ --include=*.py'],
    ['bot', 'Searching the source tree now. So far the matches are in the client wrapper, the scheduler and two test helpers; I am reading each one to see whether it retries on every exception or only on network errors, and I will summarise the differences once the scan of the remaining directories finishes'],
  ],
  needs_you: [
    ['user', 'Clean up the demo target directory.'],
    ['bot', 'The demo target is a scratch directory under /tmp that the benchmarks create. Removing it is safe, but it is a recursive delete, so I need your approval before I run it. After that I will re-run the benchmark once to confirm it recreates the directory from scratch and report the timings.'],
  ],
  error: [
    ['user', 'Summarise the last three failing builds.'],
    ['bot', 'I started collecting the logs for the three builds, then the model call was rejected before I could finish the summary. Nothing has been changed in the repository, and the partial notes below are all I have so far: build 412 failed in the linker step, build 413 in the unit tests, and build 414 has no log yet.'],
  ],
  finished_unseen: [
    ['user', 'Draft the release notes for 2.1.'],
    ['bot', 'The release notes are ready. They have four sections: the new state marks in the sidebar, the composer rim, the quieter chat field, and the accessibility fixes. Each section is two or three sentences, written for people who have never seen the 2.0 skin, and the contrast numbers are quoted exactly as measured so that nobody has to take them on trust.'],
    ['bot', 'I also added a short upgrade note: nothing in your configuration needs to change, and the five state names are unchanged.'],
  ],
}
const card = (g, G, html) => `<div style="margin:14px 0 0 24px;width:560px;border:1px solid ${G.edge};background:${G.card};border-radius:8px;padding:12px;font-size:12px">${html}</div>`

/** The conversation of a state: realistic length, wide enough to run into the right of the page. */
function chatHtml(g, G, state) {
  const msgs = TEXT[state].map(([who, t]) => who === 'user'
    ? `<div style="border:1px solid ${G.edge};background:${G.card};padding:10px 12px;border-radius:6px;margin:0 0 14px 0;max-width:760px">${t}</div>`
    : who === 'tool' ? `<div style="font:12px monospace;color:${G.mute};margin:0 0 12px 0;padding:6px 10px;border-left:2px solid ${G.edge}">$ ${t}</div>`
    : `<p style="margin:0 0 12px 0;max-width:860px">${t}</p>`).join('')
  const extra = state === 'needs_you' ? card(g, G, `<div style="color:${G.mute}">Command</div><div style="font-family:monospace;margin:8px 0">rm -rf /tmp/cuttlefish-demo-target</div><div style="text-align:right;color:${G.mute}">Reject &nbsp; <span style="border:1px solid ${G.edge};padding:3px 8px;border-radius:5px">Always allow…</span> <span style="background:#1d5cf0;color:#fff;padding:4px 10px;border-radius:5px">Run</span></div>`)
    : state === 'error' ? `<div style="margin:14px 0 0 0;width:560px;border:1px solid #d9a6ad;background:${g === 'light' ? '#fdf1f3' : '#3a2227'};color:${g === 'light' ? '#8a2b3a' : '#f0b9c1'};border-radius:8px;padding:12px;font-size:13px">Request failed (HTTP 400). The model call was rejected.</div>` : ''
  return `<div style="padding:16px 24px 0 24px;font-size:14px;line-height:1.55">${msgs}${extra}</div>`
}

/** A whole 1280×800 Desktop: sidebar with the five states, chat field of the focused state, composer rim, status strip. */
export function appHtml(g, focus) {
  const G = GROUNDS[g], W = 1280, H = 800, SB = 240, CW = W - SB, CH = H - 34 - 22
  const hue = HUES[STATES.indexOf(focus)]
  const rows = STATES.map((s, i) => rowHtml(g, s, HUES[i], s === focus, SB - 16)).join('')
  const field = fieldUrl(g, focus, hue, CW, CH, 'cf-' + focus)
  return `<html><head><style>${css}</style></head><body style="width:${W}px;height:${H}px;background:${G.side};color:${G.text};position:relative;overflow:hidden">
  <div style="position:absolute;left:0;top:0;width:${SB}px;height:${H}px;padding:60px 8px 0;background:${G.side}">
    <div style="font-size:11px;letter-spacing:.12em;color:${G.mute};margin:0 10px 10px">SESSIONS</div>${rows}</div>
  <div style="position:absolute;left:${SB}px;top:0;width:${CW}px;height:34px;background:${G.side};border-bottom:1px solid ${G.edge};font-size:11px;padding:11px 14px;letter-spacing:.04em">${TITLES[focus].toUpperCase()}</div>
  <div style="position:absolute;left:${SB}px;top:34px;width:${CW}px;height:${CH}px;background:${field} 0 0/${CW}px ${CH}px no-repeat,${G.chat};">
    ${chatHtml(g, G, focus)}
    <div style="position:absolute;left:12px;right:12px;bottom:10px"><div style="overflow:hidden">${rimHtml(g, focus, hue, CW - 24)}</div>
      <div style="height:46px;border:1px solid ${G.edge};background:${G.card};border-radius:10px;padding:13px 14px;color:${G.mute};font-size:14px;margin-top:5px">What should we tackle?</div></div></div>
  <div style="position:absolute;left:${SB}px;top:${H - 22}px;width:${CW}px;height:22px;background:${G.bar};border-top:1px solid ${G.edge};display:flex;justify-content:flex-end;align-items:center;gap:18px;padding:0 14px;font-size:11px;color:${G.mute}"><span>Smart</span><span>v0.22.7</span>${stripHtml(g, focus, hue)}</div>
  </body></html>`
}

const WORDS = {
  resting: ['resting', 'one small, soft, quiet blob', 'calm: a hairline pill above the composer'],
  working: ['working', 'a large solid cloud with a flat bottom', 'a train of cloud lobes in the pill'],
  needs_you: ['needs you', 'a FILLED chip with three bold bars (the loudest)', 'bold diagonal stripes fill the pill'],
  error: ['error', 'a HOLLOW pale grey square with a big missing corner', 'pale wash, dashed frame with gaps'],
  finished_unseen: ['finished, unseen', 'a pale disc, crisp ring, one big dark core', 'a hairline pill with one dark eye'],
}
/** The sixth cell: the legend (state → mark → rim). */
export function legendHtml(g) {
  const G = GROUNDS[g]
  const rows = STATES.map((s, i) => `<div style="display:flex;align-items:center;gap:24px;padding:14px 0;border-bottom:1px solid ${G.edge}">
    <div style="width:120px">${glyphSvg(s, HUES[i], G.chat, 3.6).replace('<svg ', '<svg style="display:block" ')}</div>
    <div style="width:140px;font-size:20px;font-weight:600">${WORDS[s][0]}</div>
    <div style="width:330px;font-size:14px;color:${G.mute}">${WORDS[s][1]}</div>
    <div style="width:520px">${rimHtml(g, s, HUES[i], 520)}<div style="font-size:12px;color:${G.mute};margin-top:4px">${WORDS[s][2]}</div></div></div>`).join('')
  return `<html><head><style>${css}</style></head><body style="width:1280px;height:800px;background:${G.chat};color:${G.text};padding:36px 48px;box-sizing:border-box">
    <div style="font-size:13px;letter-spacing:.12em;color:${G.mute};margin-bottom:6px">LEGEND · ${g.toUpperCase()} · state → mark → composer rim</div>${rows}
    <div style="margin-top:18px;font-size:13px;color:${G.mute}">Shape is the state; hue is the session (here a different hue per row only to show the two are independent). Error is the only grey mark.</div></body></html>`
}
