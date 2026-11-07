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
  calls: { loops: Array<{ wakes: number; disposed: boolean; opts: { fps?: number; idleWhen?: () => boolean } }> }
  fake: { reset(): void; emit(e: unknown): void; responder: (method: string, params?: unknown) => unknown }
  host: { state: Record<string, FakeAtom<unknown>> }
}
interface FakeCtx {
  ctx: PluginContext
  state: { contributions: Array<{ id: string; area: string; render?: () => unknown }> }
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
const { attach } = await import('../../../src/adapters/runtime.ts')

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
