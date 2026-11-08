// Unit contract of the wiring (adapters lane): attach(ctx) driven directly against the
// acceptance fakes. runtime is the one module only desktop/plugin.js imported, so this
// file pins what the wiring owes the contract at the source level: the byte-exact first
// paint for the sampled ground and viewport (with the degenerate-viewport fallback), the
// title mount owning the one <style> (a stale mount's cleanup never orphans the live
// element), root attributes tracking the focused session and its gateway events, the
// loop's idleWhen flipping with work and parking on a refetched motion:'off' config,
// foreign events ignored, and dispose undoing all of it.
//
// The fakes are plain .mjs (outside tsc's include for good reason), so they are imported
// through variable specifiers and typed by the minimal shapes used here; the loader they
// register must be live before runtime.ts resolves its SDK imports, hence the dynamic
// import at the bottom.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import type { PluginContext } from '@hermes/plugin-sdk'

interface FakeElement {
  textContent: string
  parentNode: unknown
  getAttribute(k: string): string | null
  setAttribute(k: string, v: string): void
  removeAttribute(k: string): void
}
interface FakeDocument { documentElement: FakeElement; head: { children: FakeElement[] } }
interface FakeAtom<T> { get(): T; set(v: T): void }
interface FakeSdk {
  calls: { loops: Array<{ wakes: number; disposed: boolean; opts: { fps?: number; idleWhen?: () => boolean }; draw: (t: number) => void }> }
  fake: { reset(): void; emit(e: unknown): void; responder: (method: string, params?: unknown) => unknown }
  host: { state: Record<string, FakeAtom<unknown>> }
}
interface FakeCtx {
  ctx: PluginContext
  state: { contributions: Array<{ id: string; area: string; render?: () => unknown }>; timers: Array<{ live: boolean }> }
  respondRest(fn: (path: string) => unknown): void
  advance(ms: number): Promise<void>
  dispose(): void
}
interface FakeReact { expand(node: unknown, state?: { effects: Array<() => unknown> }): { tree: unknown } }

const domPath = '../../acceptance/fake/dom.mjs'
const sdkPath = '../../acceptance/fake/sdk.mjs'
const harnessPath = '../../acceptance/fake/harness.mjs'
const reactPath = '../../acceptance/fake/react.mjs'
const { document, dom } = await import(domPath) as { document: FakeDocument; dom: { ground: string } }
const sdk = await import(sdkPath) as FakeSdk
const { makeCtx, flush } = await import(harnessPath) as {
  makeCtx(): FakeCtx
  flush(): Promise<void>
}
const { expand } = await import(reactPath) as FakeReact
const { calls, fake, host } = sdk
const { fieldCss } = await import('../../../src/adapters/painter.ts')
const { applyFeed, initialView } = await import('../../../src/adapters/view.ts')
const { attach, frameTime } = await import('../../../src/adapters/runtime.ts')

/** A ground the fallback could never guess: the fake computed style yields it verbatim. */
const GROUND_RGB = 'rgb(1, 2, 3)'
const GROUND = '#010203'
dom.ground = GROUND_RGB
const ENV = { width: 1200, height: 800, ground: GROUND, reducedMotion: false }

interface Mount { el: FakeElement; cleanup(): void }

async function boot(viewport?: { width: number; height: number }): Promise<{ h: FakeCtx; mount(): Mount }> {
  fake.reset()
  ;(globalThis as unknown as { __fakeSdk?: unknown }).__fakeSdk = sdk
  if (viewport) host.state.viewport.set(viewport)
  const h = makeCtx()
  attach(h.ctx)
  await flush()
  const title = h.state.contributions.find(c => c.id === 'title')
  const mount = (): Mount => {
    const state = { effects: [] as Array<() => unknown> }
    expand((title as { render: () => unknown }).render(), state)
    const effect = state.effects.at(-1) as () => (() => void) | void
    const cleanup = (effect() as () => void) ?? (() => {})
    return { el: document.head.children.at(-1) as FakeElement, cleanup }
  }
  return { h, mount }
}

const focusSA = async (): Promise<void> => {
  host.state.focusedSessionId.set('a')
  host.state.focusedStoredSessionId.set('SA')
  host.state.activeSessionId.set('a')
  fake.emit({ type: 'session.info', session_id: 'a', payload: { stored_session_id: 'SA' } })
  await flush()
}

const working = (): void => {
  host.state.busy.set(true)
}

const mine = (): ReturnType<typeof initialView> & { sinceChangeMs: number } => {
  const v = initialView(ENV)
  applyFeed(v, { kind: 'state', t: 0, session: 'a', payload: { gateway: 'open', busy: true, focused_session_id: 'a', focused_stored_session_id: 'SA' } })
  return v
}

test('runtime: the first paint is byte-exact for the sampled ground, and the root says resting', async () => {
  const { mount } = await boot()
  const { el } = mount()
  assert.equal(el.textContent, fieldCss(initialView(ENV)), 'the fake ground rgb(1,2,3) → #010203, never the fallback')
  assert.equal(document.documentElement.getAttribute('data-cf-state'), 'resting')
  assert.equal(document.documentElement.getAttribute('data-cf-session'), null, 'nobody focused: no session attribute, not "null"')
})

test('runtime: a degenerate viewport falls back to the window size; a 1px viewport is real', async () => {
  const zero = await boot({ width: 0, height: 0 })
  assert.ok(zero.mount().el.textContent.includes('1200px 800px'), '0 falls back')
  const one = await boot({ width: 1, height: 1 })
  assert.ok(one.mount().el.textContent.includes('1px 1px'), '1 is a viewport')
})

test('runtime: focus paints the stored id on the root and the live style follows every apply', async () => {
  const { mount } = await boot()
  const { el } = mount()
  const before = el.textContent
  await focusSA()
  assert.equal(document.documentElement.getAttribute('data-cf-session'), 'SA')
  assert.equal(document.documentElement.getAttribute('data-cf-state'), 'resting')
  assert.notEqual(el.textContent, before, 'the seed moved, so did the field — through the mounted element')
  fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: 'a',
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: true } })
  await flush()
  assert.equal(document.documentElement.getAttribute('data-cf-state'), 'needs_you', 'gateway events reach the feed, not just the atoms')
})

test('runtime: a state change arms the bloom at exactly 0 ms and wakes the one loop', async () => {
  const { mount } = await boot()
  const { el } = mount()
  await focusSA()
  const wakes = calls.loops[0].wakes
  working()
  await flush()
  const m = mine()
  assert.equal(el.textContent, fieldCss({ ...m, sinceChangeMs: 0 }), 'the pre-frame paint carries sinceChangeMs 0')
  assert.notEqual(el.textContent, fieldCss({ ...m, sinceChangeMs: 1 }))
  assert.ok(calls.loops[0].wakes > wakes, 'the change wakes the loop')
  assert.ok(calls.loops[0].opts.fps !== undefined && calls.loops[0].opts.fps <= 10)
})

test('runtime: the loop parks at rest, runs while working, and a refetched config parks it for good', async () => {
  const { h, mount } = await boot()
  mount()
  const idle = (): boolean => calls.loops[0].opts.idleWhen?.() ?? false
  assert.equal(idle(), true, 'resting parks')
  await focusSA()
  working()
  await flush()
  assert.equal(idle(), false, 'working clouds run')

  let mtime = 7
  let configs = 0
  fake.responder = (method: string): unknown => (method === 'config.get' ? { mtime } : { sessions: [] })
  h.respondRest((path: string) => {
    if (path === '/config') { configs += 1; return configs === 1 ? { settings: { motion: 'off' }, warnings: [], rev: 'r' } : null }
    if (path === '/health') return { ok: true }
    return { mtime }
  })
  await h.advance(50)
  assert.equal(configs, 1, 'the kick refetched the config')
  host.state.busy.set(false)
  host.state.busyBySession.set({ a: true })
  await flush()
  assert.equal(idle(), true, 'motion off from a live config parks even a fresh state change')

  mtime = 8
  await h.advance(2000)
  assert.equal(configs, 2, 'the mtime change refetched again — a null answer resets to defaults')
  host.state.busyBySession.set({ a: false })
  host.state.busy.set(true)
  await flush()
  assert.equal(idle(), false, 'defaults restored: a fresh state change blooms again')
})

test('runtime: a stale mount\'s cleanup never orphans the live style', async () => {
  const { mount } = await boot()
  const first = mount()
  const second = mount()
  first.cleanup()
  const before = second.el.textContent
  await focusSA()
  assert.notEqual(second.el.textContent, before, 'the live element still repaints')
  assert.equal(first.el.parentNode, null, 'the stale element was removed')
})

test('runtime: a foreign event is ignored; dispose removes the style and the root attributes', async () => {
  const { h, mount } = await boot()
  const { el } = mount()
  fake.emit({ type: 'unrelated.event', session_id: 'x', payload: {} })
  await flush()
  await focusSA()
  h.dispose()
  assert.equal(el.parentNode, null, 'dispose removes the owned style')
  assert.equal(document.documentElement.getAttribute('data-cf-state'), null)
  assert.equal(document.documentElement.getAttribute('data-cf-session'), null)
  assert.equal(calls.loops[0].disposed, true, 'the loop is disposed')
})

// ---- review round (F1, F3, F5, F7) -------------------------------------------------------------

const ringOfCss = (css: string): string => /--dt-composer-ring:([^;}]+)/.exec(css)?.[1] ?? ''

test('runtime: the ground is what the engine RESOLVES, not the custom property\'s token stream (F1)', async () => {
  const real = globalThis.getComputedStyle
  // v0.22.7: --ui-chat-surface-background is var(--ui-bg-chrome) = color-mix(…); a probe's background-color resolves it
  ;(globalThis as unknown as { getComputedStyle: unknown }).getComputedStyle = () => ({
    getPropertyValue: () => 'color-mix(in srgb, #fbfbfa 92%, #ffffff)',
    backgroundColor: 'color(srgb 0.980392 0.976471 0.968627)',
  })
  try {
    const { mount } = await boot()
    const { el } = mount()
    const light = initialView({ ...ENV, ground: '#faf9f7' })
    assert.equal(el.textContent, fieldCss(light), 'painted on the light theme\'s ground, not the dark fallback')
  } finally {
    ;(globalThis as unknown as { getComputedStyle: unknown }).getComputedStyle = real
  }
})

test('runtime: the composer ring is the identity hue in EVERY state (F5)', async () => {
  const { mount } = await boot()
  const { el } = mount()
  await focusSA()
  const rest = ringOfCss(el.textContent)
  assert.ok(rest.length > 0)
  working()
  await flush()
  assert.equal(document.documentElement.getAttribute('data-cf-state'), 'working')
  assert.equal(ringOfCss(el.textContent), rest, 'working')
  host.state.busy.set(false)
  fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: 'a',
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: true } })
  await flush()
  assert.equal(ringOfCss(el.textContent), rest, 'needs you')
  fake.emit({ type: 'plugin.cuttlefish-theme.needs_you', session_id: 'a',
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: false } })
  fake.emit({ type: 'plugin.cuttlefish-theme.error', session_id: '', payload: { session_id: 'SA', session_key: 'SA', retryable: false } })
  await flush()
  assert.equal(document.documentElement.getAttribute('data-cf-state'), 'error')
  assert.equal(ringOfCss(el.textContent), rest, 'error')
})

test('runtime: leaving reduced motion while working wakes the parked loop (F3)', async () => {
  const { mount } = await boot()
  mount()
  await focusSA()
  working()
  await flush()
  const idle = (): boolean => calls.loops[0].opts.idleWhen?.() ?? false
  assert.equal(idle(), false)
  const fire = (matches: boolean): void => { for (const fn of (dom as unknown as { mediaListeners: Set<(e: { matches: boolean }) => void> }).mediaListeners) fn({ matches }) }
  fire(true)
  assert.equal(idle(), true, 'reduced motion parks')
  const wakes = calls.loops[0].wakes
  fire(false)
  assert.equal(idle(), false, 'clouds are wanted again')
  assert.ok(calls.loops[0].wakes > wakes, 'and the parked loop is woken — no state change needed')
})

test('runtime: a refetched config that re-enables motion wakes the loop while working (F3)', async () => {
  const { h, mount } = await boot()
  mount()
  await focusSA()
  working()
  await flush()
  let mtime = 1
  let configs = 0
  fake.responder = (method: string): unknown => (method === 'config.get' ? { mtime } : { sessions: [] })
  h.respondRest((path: string) => {
    if (path === '/config') { configs += 1; return { settings: { motion: configs === 1 ? 'off' : 'still' }, warnings: [], rev: 'r' } }
    if (path === '/health') return { ok: true }
    return { mtime }
  })
  await h.advance(50)
  assert.equal(calls.loops[0].opts.idleWhen?.(), true, 'motion off parks')
  const wakes = calls.loops[0].wakes
  mtime = 2
  await h.advance(2000)
  assert.equal(calls.loops[0].opts.idleWhen?.(), false)
  assert.ok(calls.loops[0].wakes > wakes, 'motion back on wakes it')
})

test('runtime: a live viewport of 0 keeps the window-size fallback, like the first sight (F7)', async () => {
  const { mount } = await boot()
  const { el } = mount()
  host.state.viewport.set({ width: 0, height: 0 })
  await flush()
  assert.ok(el.textContent.includes('1200px 800px'), 'not a 0px field')
  host.state.viewport.set({ width: 900, height: 700 })
  await flush()
  assert.ok(el.textContent.includes('900px 700px'))
})

test('runtime: dispose leaves no style, attribute, timer, listener, loop or live contribution; a second life never doubles (hot reload)', async () => {
  const fakeSdk = sdk as unknown as { fake: { listenerCount(): number }; host: { state: Record<string, { lc: number }> } }
  const media = (dom as unknown as { mediaListeners: Set<unknown> }).mediaListeners
  const styles = (): number => document.head.children.filter(c => (c as unknown as { tagName: string }).tagName === 'STYLE').length
  const base = styles()
  const mediaBase = media.size
  const atomBase = Object.fromEntries(Object.entries(fakeSdk.host.state).map(([k, a]) => [k, a.lc]))
  const life = async (): Promise<FakeCtx> => {
    const { h, mount } = await boot()
    mount()
    assert.equal(styles(), base + 1, 'exactly ONE owned style in a life')
    await focusSA()
    assert.equal(fakeSdk.fake.listenerCount(), 1, 'one event listener')
    assert.equal(media.size, mediaBase + 1, 'one matchMedia listener in a life')
    assert.equal(h.state.contributions.filter(c => (c as { live?: boolean }).live).length, 4, 'four live contributions')
    assert.equal(h.state.timers.filter(t => t.live).length, 3, 'one kick, one watch, one poll')
    return h
  }
  const gone = (h: FakeCtx, loops: number): void => {
    h.dispose()
    assert.equal(styles(), base, 'no style of ours')
    assert.equal(document.documentElement.getAttribute('data-cf-state'), null)
    assert.equal(document.documentElement.getAttribute('data-cf-session'), null)
    assert.equal(h.state.timers.filter(t => t.live).length, 0, 'no timer')
    assert.equal(fakeSdk.fake.listenerCount(), 0, 'no event listener')
    assert.equal(media.size, mediaBase, 'no matchMedia listener of ours')
    for (const [name, atom] of Object.entries(fakeSdk.host.state)) assert.equal(atom.lc, atomBase[name], `no listener of ours left on host.state.${name}`)
    assert.equal(h.state.contributions.filter(c => (c as { live?: boolean }).live).length, 0, 'no contribution')
    assert.equal(calls.loops.length, loops)
    assert.ok(calls.loops.every(l => l.disposed), 'every loop disposed')
  }
  gone(await life(), 1)
  gone(await life(), 1) // boot() resets the recorder: the second life has exactly ONE loop of its own, again
})

// ---- F8: a live light/dark switch --------------------------------------------------------------

test('runtime: the ground is re-sampled on the config tick — a theme switch re-renders field and rim, no change re-renders nothing (F8)', async () => {
  const real = globalThis.getComputedStyle
  const host_ = { ground: 'rgb(20, 20, 22)' }
  ;(globalThis as unknown as { getComputedStyle: unknown }).getComputedStyle = () => ({
    getPropertyValue: () => '', backgroundColor: host_.ground,
  })
  try {
    const { h, mount } = await boot()
    h.respondRest((path: string) => (path === '/config' ? { settings: {}, warnings: [], rev: 'r' } : path === '/health' ? { ok: true } : { mtime: 1 }))
    fake.responder = (method: string): unknown => (method === 'config.get' ? { mtime: 1 } : { sessions: [] })
    const { el } = mount()
    await h.advance(50) // the kick: first config sight
    let writes = 0
    let text = el.textContent
    Object.defineProperty(el, 'textContent', { get: () => text, set: (x: string) => { writes += 1; text = x } })
    const rim = (): string => JSON.stringify(expand((h.state.contributions.find(c => c.id === 'rim') as { render: () => unknown }).render()).tree)
    const dark = text
    const darkRim = rim()
    const wakes = calls.loops[0].wakes

    await h.advance(2000) // a tick, ground unchanged
    assert.equal(writes, 0, 'no change ⇒ not one re-render')
    assert.equal(calls.loops[0].wakes, wakes)
    assert.equal(calls.loops[0].opts.idleWhen?.(), true, 'the loop stays parked')

    host_.ground = 'rgb(250, 249, 247)' // the user flips to a light theme
    await h.advance(2000)
    assert.equal(text, fieldCss(initialView({ ...ENV, ground: '#faf9f7' })), 'the field is tuned to the new ground')
    assert.notEqual(text, dark)
    assert.notEqual(rim(), darkRim, 'the rim follows')
    const settled = text
    await h.advance(2000)
    assert.equal(text, settled, 'and settles: the same ground again changes nothing')
  } finally {
    ;(globalThis as unknown as { getComputedStyle: unknown }).getComputedStyle = real
  }
})

test('runtime D3: at rest NOTHING re-renders — health polls, repeated atom values and foreign events write no style (fix-m4)', async () => {
  const { h, mount } = await boot()
  h.respondRest((path: string) => (path === '/config' ? { settings: {}, warnings: [], rev: 'r' } : path === '/health' ? { ok: true } : { mtime: 1 }))
  fake.responder = (method: string): unknown => (method === 'config.get' ? { mtime: 1 } : { sessions: [] })
  const { el } = mount()
  await focusSA()
  await h.advance(50)
  await h.advance(5100) // first health sight flips pluginSeen/healthOk once
  let writes = 0
  let text = el.textContent
  Object.defineProperty(el, 'textContent', { get: () => text, set: (x: string) => { writes += 1; text = x } })
  host.state.busy.set(false) // the same value again
  host.state.focusedStoredSessionId.set('SA')
  fake.emit({ type: 'gateway.something', session_id: 'a', payload: {} })
  await h.advance(12000) // two health ticks, six config ticks
  assert.equal(writes, 0, 'an unchanged view is not rewritten')
})

test('runtime D3: working frames sit on a 250 ms grid and repeat every cloud cycle, so the engine re-uses its decoded images (fix-m4)', async () => {
  const { mount } = await boot()
  const { el } = mount()
  await focusSA()
  working()
  await flush()
  const frame = (t: number): string => { calls.loops[0].draw(t); return el.textContent }
  frame(0) // anchors the state-change bloom; the checks below are after it (> 2.4 s), where only the clouds move
  const a = frame(10000)
  assert.equal(frame(10240), a, 'inside one 250 ms bucket the picture is the same')
  const b = frame(10250)
  assert.notEqual(b, a, 'the next bucket moves the cloud')
  assert.equal(frame(10000 + 18000), a, 'one cloud cycle later the very same text (a cacheable image)')
  assert.equal(frame(10250 + 5 * 18000), b)
  assert.equal(frame(10000), a, 'and a replay is exact')
})

test('runtime D3: frameTime puts frames on the 250 ms grid and wraps them at the cloud cycle — except under alive, whose twinkles keep their own periods', () => {
  assert.equal(frameTime(10240, 'still'), 10000)
  assert.equal(frameTime(10250, 'still'), 10250)
  assert.equal(frameTime(10000 + 36000, 'still'), 10000)
  assert.equal(frameTime(10000 + 36000, 'off'), 10000)
  assert.equal(frameTime(46240, 'alive'), 46000, 'alive: grid only, no wrap')
})

test('runtime D3: between frames the loop PARKS (no 60 Hz rAF spin) and a scoped timer wakes it for the next one (fix-m4)', async () => {
  const { h, mount } = await boot()
  mount()
  await focusSA()
  working()
  await flush()
  const loop = calls.loops[0]
  assert.equal(loop.opts.idleWhen?.(), false, 'a wanted frame is not yet drawn: not parked')
  loop.draw(10_000)
  assert.equal(loop.opts.idleWhen?.(), true, 'the loop\'s own check right after a frame: park, zero pending rAF')
  assert.equal(loop.opts.idleWhen?.(), false, 'and only that one check — any later look says the clouds are wanted')
  const wakes = loop.wakes
  await h.advance(100)
  assert.equal(loop.wakes, wakes, 'not woken early')
  await h.advance(140)
  assert.equal(loop.wakes, wakes + 1, 'woken once, ~240 ms after the frame')
  assert.equal(loop.opts.idleWhen?.(), false, 'ready for the next frame')
  loop.draw(10_250)
  loop.draw(10_500) // a second frame arriving while the first timer was pending replaces it, never stacks
  await h.advance(240)
  assert.equal(loop.wakes, wakes + 2, 'one timer per frame, never two')
})

test('runtime D3: dispose cancels the pacing timer — none outlives the plugin', async () => {
  const { h, mount } = await boot()
  mount()
  await focusSA()
  working()
  await flush()
  calls.loops[0].draw(10_000)
  assert.ok(h.state.timers.some(t => t.live), 'a pacing timer is pending after a frame')
  h.dispose()
  assert.ok(h.state.timers.every(t => !t.live), 'no pacing timer outlives the plugin')
})
