// ACCEPTANCE CONTRACT PART — observation helpers for oA_part1_applied / oA_part2_added_state (locked).
// NEW file beside the locked fakes: it only OBSERVES through what the locked fake host already exposes
// (`sdk.calls.loops` records each createBudgetedLoop's draw callback, options and wake count). It never edits a fake.
//   - `boot`/`focus`/`busy`/`mountTitlebar`/`swatch`/`stripText`: the same driving the locked oA_adapters.test.ts does.
//   - `LoopDriver`: plays the part of requestAnimationFrame for the budgeted loops, with the REAL semantics of
//     apps/desktop/src/lib/budgeted-loop.ts (v0.22.7): draw first, THEN check idleWhen and park; a wake() un-parks.
//   - CSS helpers: strip comments, parse rules (at-rules recursed), decode a data:image/svg+xml url().
import { setReducedMotion, document as fakeDocument } from './dom.mjs'
import { flush, loadPlugin } from './harness.mjs'
import { expand, walk } from './react.mjs'

export { setReducedMotion, fakeDocument, flush, expand, walk }

/** Load the shipped plugin.js under the fake host; `settings` is what /config answers (mutable via the returned box). */
export async function boot({ settings = {}, health = true } = {}) {
  const { h, sdk } = await loadPlugin()
  const box = { settings, mtime: 1, health }
  h.respondRest(path => answerRest(box, path))
  sdk.fake.responder = (method, params) => {
    if (method === 'config.get' && params?.key === 'mtime') return { mtime: box.mtime }
    if (method === 'session.active_list') return { sessions: [] }
    return {}
  }
  await h.advance(10)
  return { h, sdk, box }
}

function answerRest(box, path) {
  if (path === '/health') {
    if (!box.health) throw new Error('404')
    return { ok: true, version: '2.0.0' }
  }
  if (path === '/config') return { settings: box.settings, warnings: [], rev: String(box.mtime) }
  throw new Error(`unexpected rest ${path}`)
}

export function focus(sdk, rt, stored) {
  sdk.host.state.focusedSessionId.set(rt)
  sdk.host.state.focusedStoredSessionId.set(stored)
  sdk.host.state.activeSessionId.set(rt)
  sdk.fake.emit({ type: 'session.info', session_id: rt, payload: { stored_session_id: stored } })
}
export const busy = (sdk, map) => sdk.host.state.busyBySession.set(map)

export function mountTitlebar(h) {
  const mounts = h.live(a => a.startsWith('titleBar.'))
  if (mounts.length < 1) throw new Error('a title-bar permanent mount owns the injected style')
  const cleanups = []
  for (const m of mounts) {
    if (!m.render) continue
    const { effects } = expand(m.render())
    for (const e of effects) { const c = e(); if (typeof c === 'function') cleanups.push(c) }
  }
  return cleanups
}

export const ownStyles = () => fakeDocument.head.children.filter(c => c.tagName === 'STYLE')
/** All CSS the plugin currently owns (connected <style> elements, concatenated). */
export const currentCss = () => ownStyles().map(s => s.textContent).join('\n')

export function swatchRoot(h, sessionId) {
  const rows = h.live(a => a === 'sessionRow.leading' || a === 'sessionRow.trailing')
  if (rows.length !== 1) throw new Error(`exactly one session-row slot, got ${rows.length}`)
  const out = rows[0].data.render({ sessionId })
  if (!out) throw new Error(`the row slot rendered nothing for ${sessionId}`)
  const root = walk(expand(out).tree).find(e => e.props?.['data-cf-session'] !== undefined)
  if (!root) throw new Error('the swatch root carries data-cf-session')
  return root
}

/** Every string/number leaf under a rendered tree, joined: the words a person could read. */
export function textOf(tree) {
  if (tree === null || tree === undefined || typeof tree === 'boolean') return ''
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree)
  if (Array.isArray(tree)) return tree.map(textOf).filter(Boolean).join(' ')
  return textOf(tree.props?.children)
}

/** The status-bar items' readable text (what a person reads in the strip), whitespace-normalised. */
export function stripText(h) {
  const items = h.live(a => a.startsWith('statusBar.'))
  return items.map(s => textOf(expand(s.render ? s.render() : s.data).tree)).join(' ').replace(/\s+/g, ' ').trim()
}

/** The strip's full serialisation (words + attributes + drawn dots), for "did anything change". */
export function stripMarkup(h) {
  return h.live(a => a.startsWith('statusBar.')).map(s => JSON.stringify(expand(s.render ? s.render() : s.data).tree)).join('')
}

/** The composer.top contributions (COMPOSER_AREAS.top, exported by the locked fake sdk): the plugin's rim. */
export function rimItems(h) { return h.live(a => a === 'composer.top') }

/** The rim's rendered root: the first host element carrying data-cf-state, plus its serialised markup. */
export function rimRoot(h) {
  const items = rimItems(h)
  if (items.length < 1) throw new Error('no contribution in COMPOSER_AREAS.top (composer.top)')
  const tree = expand(items[0].render ? items[0].render({}) : items[0].data).tree
  const root = walk(tree).find(e => e.props?.['data-cf-state'] !== undefined)
  if (!root) throw new Error('the rim root carries no data-cf-state')
  return { root, state: root.props['data-cf-state'], markup: JSON.stringify(root), drawsSvg: /"type":"svg"|data:image\/svg|<svg/.test(JSON.stringify(root)) }
}

// ---- frames --------------------------------------------------------------------------------------------------------

export class LoopDriver {
  constructor(sdk) { this.sdk = sdk; this.t = 0; this.state = new Map(); this.draws = 0 }

  /** Run frames for `ms` of manual-clock time, advancing the ctx timers in the same steps. Returns the draws made. */
  async run(h, ms) {
    const before = this.draws
    const end = this.t + ms
    while (this.t < end) {
      const fps = Math.min(...this.live().map(r => r.opts.fps ?? 15), 60)
      const step = Math.max(1, Math.round(1000 / (Number.isFinite(fps) ? fps : 10)))
      await h.advance(step)
      this.t += step
      this.tick()
    }
    return this.draws - before
  }

  live() { return this.sdk.calls.loops.filter(r => !r.disposed) }

  tick() {
    for (const rec of this.live()) this.step(rec)
  }

  /** One rAF tick of one loop, with budgeted-loop.ts semantics: draw (if the fps budget allows), THEN park if idle. */
  step(rec) {
    const s = this.state.get(rec) ?? { dormant: false, seenWakes: 0, lastDraw: -Infinity }
    this.state.set(rec, s)
    if (s.dormant && rec.wakes > s.seenWakes) s.dormant = false
    s.seenWakes = rec.wakes
    if (s.dormant) return
    if (this.t - s.lastDraw >= 1000 / (rec.opts.fps ?? 15)) {
      rec.draw(this.t)
      s.lastDraw = this.t
      this.draws++
    }
    if (rec.opts.idleWhen?.()) s.dormant = true
  }
}

// ---- CSS -----------------------------------------------------------------------------------------------------------

export const stripCssComments = css => css.replace(/\/\*[\s\S]*?\*\//g, '')

/** Indexes of the characters of `text` (from `from`) that sit outside quotes and parentheses: data URIs carry `;` `(` `)` `'` `"`. */
function* topLevel(text, from = 0) {
  let depth = 0
  let quote = ''
  for (let i = from; i < text.length; i++) {
    const ch = text[i]
    if (quote) { if (ch === quote) quote = ''; continue }
    if (ch === '"' || ch === "'") { quote = ch; continue }
    if (ch === '(') { depth++; continue }
    if (ch === ')') { depth--; continue }
    if (depth === 0) yield i
  }
}

/** Split `a:b;c:d` at top-level semicolons. */
function splitDeclarations(body) {
  const out = []
  let start = 0
  for (const i of topLevel(body)) {
    if (body[i] !== ';') continue
    out.push(body.slice(start, i))
    start = i + 1
  }
  if (body.slice(start).trim()) out.push(body.slice(start))
  return out
}

/** Find the `}` that closes the block opened just before `from`. */
function matchBrace(text, from) {
  let depth = 1
  for (const i of topLevel(text, from)) {
    if (text[i] === '{') depth++
    if (text[i] === '}' && --depth === 0) return i
  }
  throw new Error('unbalanced braces in css')
}

/** Rules of a stylesheet (comments already stripped): [{ selectors: string[], decls: {prop: value}[], at: string|null }]. */
export function parseRules(css, at = null) {
  const rules = []
  let i = 0
  while (i < css.length) {
    const open = css.indexOf('{', i)
    if (open < 0) break
    const head = css.slice(i, open).trim()
    const close = matchBrace(css, open + 1)
    const body = css.slice(open + 1, close)
    if (head.startsWith('@')) rules.push(...parseRules(body, head))
    else {
      const decls = splitDeclarations(body).map(d => {
        const at2 = d.indexOf(':')
        return at2 < 0 ? null : { prop: d.slice(0, at2).trim().toLowerCase(), value: d.slice(at2 + 1).trim() }
      }).filter(Boolean)
      rules.push({ selectors: head.split(',').map(s => s.trim()).filter(Boolean), decls, at })
    }
    i = close + 1
  }
  return rules
}

/** The data:image/svg+xml url() payloads in a declaration value, decoded to SVG text. */
export function svgDataUris(value) {
  const out = []
  const re = /url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*?))\s*\)/gi
  for (const m of value.matchAll(re)) {
    const uri = m[1] ?? m[2] ?? m[3] ?? ''
    const head = /^data:image\/svg\+xml((?:;[a-z0-9=-]+)*),/i.exec(uri)
    if (!head) continue
    const payload = uri.slice(head[0].length)
    try { out.push(/;base64/i.test(head[1]) ? Buffer.from(payload, 'base64').toString('utf8') : decodeURIComponent(payload)) }
    catch { out.push(payload) }
  }
  return out
}

/** Split a declaration value at top-level commas (background layers). */
export function splitLayers(value) {
  const out = []
  let start = 0
  for (const i of topLevel(value)) {
    if (value[i] !== ',') continue
    out.push(value.slice(start, i).trim())
    start = i + 1
  }
  out.push(value.slice(start).trim())
  return out
}

/** Decoded SVGs of the `background` shorthand (only) on rules that target [data-chat-surface]. */
export function backgroundLayers(css) {
  const out = []
  for (const r of parseRules(stripCssComments(css))) {
    if (!r.selectors.some(s => s.includes('[data-chat-surface]'))) continue
    for (const d of r.decls) if (d.prop === 'background') out.push(...svgDataUris(d.value))
  }
  return out
}

export const countCircles = svg => (svg.match(/<circle\b/gi) ?? []).length

/** Declarations of `prop` across all rules whose selector list satisfies `selectorTest` (comments stripped, in order). */
export function declarations(css, prop, selectorTest = () => true) {
  const out = []
  for (const r of parseRules(stripCssComments(css))) {
    if (!r.selectors.some(selectorTest)) continue
    for (const d of r.decls) if (d.prop === prop) out.push(d.value)
  }
  return out
}

/** The field layers: decoded SVGs painted as background-image on a rule that targets [data-chat-surface]. */
export function fieldLayers(css) {
  const out = []
  for (const r of parseRules(stripCssComments(css))) {
    if (!r.selectors.some(s => s.includes('[data-chat-surface]'))) continue
    for (const d of r.decls) if (d.prop === 'background-image' || d.prop === 'background') out.push(...svgDataUris(d.value))
  }
  return out
}
