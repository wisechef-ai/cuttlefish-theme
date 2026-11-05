// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT — the desktop adapters, loaded from the SHIPPED bundle desktop/plugin.js under a fake host (locked).
// SPEC C1/C6 surfaces, C3 motion, C5 live config, C9 needs-you, catalog rule 8. Contract/README.md §Adapters names
// the DOM hooks asserted here (data-cf-state / data-cf-session on the swatch root; html[data-cf-*]).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { setReducedMotion, document as fakeDocument } from './fake/dom.mjs'
import { flush, loadPlugin } from './fake/harness.mjs'
import { expand, walk } from './fake/react.mjs'

const SETTINGS_DEFAULT = { settings: {}, warnings: [], rev: 'a' }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function boot(opts: { health?: boolean; settings?: () => any; mtime?: () => any } = {}) {
  const { mod, h, sdk } = await loadPlugin()
  void mod
  const health = opts.health ?? true
  h.respondRest((path: string) => {
    if (path === '/health') { if (!health) throw new Error('404'); return { ok: true, version: '2.0.0' } }
    if (path === '/config') return (opts.settings ?? (() => SETTINGS_DEFAULT))()
    throw new Error(`unexpected rest ${path}`)
  })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sdk.fake.responder = (method: string, params: any) => {
    if (method === 'config.get' && params?.key === 'mtime') return { mtime: (opts.mtime ?? (() => 1))() }
    if (method === 'session.active_list') return { sessions: [] }
    return {}
  }
  await h.advance(10)
  return { h, sdk }
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rowSlot = (h: any) => {
  const rows = h.live((a: string) => a === 'sessionRow.leading' || a === 'sessionRow.trailing')
  assert.equal(rows.length, 1, `exactly one session-row slot, got ${rows.length}`)
  return rows[0]
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function swatch(h: any, sessionId: string) {
  const out = rowSlot(h).data.render({ sessionId })
  assert.ok(out, `the row slot rendered nothing for ${sessionId}: every session gets a swatch`)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const root = walk(expand(out).tree).find((e: any) => e.props?.['data-cf-session'] !== undefined)
  assert.ok(root, 'the swatch root carries data-cf-session')
  assert.equal(root.props['data-cf-session'], sessionId)
  return root
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const markup = (el: any) => JSON.stringify(el)

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mountTitlebar(h: any) {
  const mounts = h.live((a: string) => a.startsWith('titleBar.'))
  assert.ok(mounts.length >= 1, 'a title-bar permanent mount owns the injected style')
  const cleanups: (() => void)[] = []
  for (const m of mounts) {
    if (!m.render) continue
    const { effects } = expand(m.render())
    for (const e of effects) { const c = e(); if (typeof c === 'function') cleanups.push(c) }
  }
  return cleanups
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ownStyles = () => fakeDocument.head.children.filter((c: any) => c.tagName === 'STYLE')

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function focus(sdk: any, rt: string, stored: string) {
  sdk.host.state.focusedSessionId.set(rt)
  sdk.host.state.focusedStoredSessionId.set(stored)
  sdk.host.state.activeSessionId.set(rt)
  sdk.fake.emit({ type: 'session.info', session_id: rt, payload: { stored_session_id: stored } })
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function busy(sdk: any, map: Record<string, boolean>) { sdk.host.state.busyBySession.set(map) }

test('A1 the bundle is one self-contained ESM plugin with the right id', async () => {
  const { mod } = await loadPlugin()
  assert.equal(mod.default.id, 'cuttlefish-theme')
  assert.equal(typeof mod.default.register, 'function')
  assert.ok(typeof mod.default.name === 'string' && mod.default.name.length > 0)
})

test('A2 surfaces: one row slot, a status-bar strip, a title-bar mount; no pane (the field is not a pane)', async () => {
  const { h } = await boot()
  rowSlot(h)
  assert.ok(h.live((a: string) => a.startsWith('statusBar.')).length >= 1, 'status strip')
  assert.ok(h.live((a: string) => a.startsWith('titleBar.')).length >= 1, 'title-bar mount')
  assert.equal(h.live('panes').length, 0, 'no pane')
})

test('A3 every session row gets a swatch that tracks its own state', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  sdk.fake.emit({ type: 'session.info', session_id: 'b', payload: { stored_session_id: 'SB' } })
  for (const id of ['SA', 'SB', 'never-seen-before']) assert.equal(swatch(h, id).props['data-cf-state'], 'resting')
  busy(sdk, { b: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'b', payload: {} })
  await flush()
  assert.equal(swatch(h, 'SB').props['data-cf-state'], 'working')
  sdk.fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: '',
    payload: { session_id: 'SB', session_key: 'SB', request_id: 'r1', kind: 'approval', active: true } })
  await flush()
  assert.equal(swatch(h, 'SB').props['data-cf-state'], 'needs_you')
  assert.equal(swatch(h, 'SA').props['data-cf-state'], 'resting', 'never leaks into another row')
  assert.match(markup(swatch(h, 'SB')), /svg|data:image\/svg\+xml/, 'the swatch draws the dots')
})

test('A4 the background field + composer ring live in ONE owned <style>, on documented hooks only; dispose removes all', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  await flush()
  const cleanups = mountTitlebar(h)
  await flush()
  const styles = ownStyles()
  assert.equal(styles.length, 1, `exactly one owned <style>, found ${styles.length}`)
  const css = styles[0].textContent
  assert.match(css, /\[data-chat-surface\]/, 'the field paints the documented chat-surface hook')
  assert.match(css, /data:image\/svg\+xml/, 'the field is the organ scatter (an SVG image layer), not a fill')
  assert.match(css, /--dt-composer-ring/, 'the composer ring speaks the language')
  assert.doesNotMatch(css, /data-(slot|testid|sidebar|tour)\b/, 'no undocumented core markup in the CSS')
  assert.doesNotMatch(css, /background-color\s*:/, 'the user\'s own ground stays: no background-color override')
  assert.equal(fakeDocument.documentElement.getAttribute('data-cf-state'), 'resting')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(100)
  assert.equal(fakeDocument.documentElement.getAttribute('data-cf-state'), 'working', 'the root reflects the FOCUSED session')
  for (const c of cleanups) c()
  h.dispose()
  await flush()
  assert.equal(ownStyles().filter((s: { isConnected: boolean }) => s.isConnected).length, 0, 'the style is gone after dispose')
  const left = Object.keys(fakeDocument.documentElement.attributes).filter(k => k.startsWith('data-cf'))
  assert.deepEqual(left, [], 'html[data-cf-*] attributes are removed on dispose')
})

test('A5 one budgeted loop: ≤ 10 fps, dormant at rest, awake while working, dormant again under reduced motion', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  await h.advance(5000)
  const live = sdk.calls.loops.filter((l: { disposed: boolean }) => !l.disposed)
  assert.equal(live.length, 1, `exactly one live createBudgetedLoop, found ${live.length}`)
  const loop = live[0]
  assert.ok((loop.opts.fps ?? 15) <= 10, `fps ${loop.opts.fps}`)
  assert.equal(typeof loop.opts.idleWhen, 'function', 'the loop declares idleWhen (idle dormancy)')
  assert.equal(loop.opts.idleWhen(), true, 'resting + still: the loop is parked')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(5000)
  assert.equal(loop.opts.idleWhen(), false, 'working: the clouds move')
  assert.ok(loop.wakes >= 1, 'a state change wakes the loop')
  setReducedMotion(true)
  await flush()
  assert.equal(loop.opts.idleWhen(), true, 'prefers-reduced-motion parks it, live')
  setReducedMotion(false)
  h.dispose()
  assert.ok(loop.disposed, 'the loop is disposed with the plugin')
})

test('A6 the Python half off → active_list polling ≥ 3 s apart finds needs-you; on → no polling', async () => {
  const off = await boot({ health: false })
  focus(off.sdk, 'a', 'SA')
  off.sdk.fake.responder = (method: string, params: { key?: string }) => {
    if (method === 'config.get' && params?.key === 'mtime') return { mtime: 1 }
    if (method === 'session.active_list') return { sessions: [{ id: 'b', session_key: 'SB', status: 'waiting' }] }
    return {}
  }
  await off.h.advance(20_000)
  const polls = off.sdk.calls.requests.filter((r: { method: string }) => r.method === 'session.active_list')
  assert.ok(polls.length >= 2 && polls.length <= 7, `${polls.length} polls in 20 s (3–10 s apart expected)`)
  assert.equal(swatch(off.h, 'SB').props['data-cf-state'], 'needs_you', 'the poll alone drives needs-you')
  for (const t of off.h.state.timers.filter((x: { kind: string; live: boolean }) => x.kind === 'interval' && x.live)) {
    assert.ok(t.ms >= 2000, `an interval of ${t.ms} ms is faster than the SDK allows`)
  }
  off.h.dispose()
  const on = await boot({ health: true })
  await on.h.advance(20_000)
  assert.equal(on.sdk.calls.requests.filter((r: { method: string }) => r.method === 'session.active_list').length, 0)
  on.h.dispose()
})

test('A7 config applies live: an mtime change refetches /config and the swatches + motion follow, no re-register', async () => {
  let mtime = 1
  let settings: Record<string, unknown> = {}
  const { h, sdk } = await boot({ mtime: () => mtime, settings: () => ({ settings, warnings: [], rev: String(mtime) }) })
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  sdk.fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: '',
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: true } })
  await h.advance(100)
  const before = markup(swatch(h, 'SA'))
  const registered = h.state.contributions.length
  settings = { states: { needs_you: { pattern: 'mottle' } }, motion: 'off' }
  mtime = 2
  await h.advance(12_000)
  assert.ok(h.state.rest.filter((r: { path: string }) => r.path === '/config').length >= 2, 'the new mtime triggered a refetch')
  assert.notEqual(markup(swatch(h, 'SA')), before, 'the remapped pattern shows without a restart')
  assert.equal(h.state.contributions.length, registered, 'applied in place, not by re-registering')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(2000)
  const loop = sdk.calls.loops.find((l: { disposed: boolean }) => !l.disposed)
  assert.ok(!loop || loop.opts.idleWhen() === true, 'motion: off from config parks the loop')
  h.dispose()
})

test('A8 the user owns colours and theme: no setColor, no requestTheme, no accent override', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(10_000)
  assert.deepEqual(sdk.calls.setColor, [])
  assert.deepEqual(sdk.calls.requestTheme, [])
  assert.deepEqual(sdk.calls.accent, [])
  h.dispose()
})

test('A9 dispose leaves nothing behind: timers, listeners, loop', async () => {
  const { h, sdk } = await boot({ health: false })
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  await h.advance(15_000)
  h.dispose()
  await flush()
  assert.equal(h.state.timers.filter((t: { live: boolean }) => t.live).length, 0, 'a timer survived dispose')
  assert.equal(h.state.listeners.filter((l: { live: boolean }) => l.live).length, 0, 'a DOM listener survived dispose')
  assert.equal(sdk.fake.listenerCount(), 0, 'a host.onEvent listener survived dispose')
  assert.ok(sdk.calls.loops.every((l: { disposed: boolean }) => l.disposed), 'a loop survived dispose')
})

test('A10 the status strip names the focused state in words (literal redundancy), from settings labels', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  sdk.fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: '',
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: true } })
  await h.advance(100)
  const strip = h.live((a: string) => a.startsWith('statusBar.'))[0]
  const text = JSON.stringify(expand(strip.render ? strip.render() : strip.data).tree)
  assert.match(text, /needs you/, 'the strip says "needs you"')
})
