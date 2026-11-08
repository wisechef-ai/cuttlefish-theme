// Unit contract of the surface registrations (adapters lane): exactly four
// contributions at the SDK areas — every sidebar row's swatch, the status
// strip, the composer rim, the title-bar style mount — each at order 0, the
// chip showing the state's own words (and '' for a state the settings do not
// name, never a throw), and one disposer removing every registration. The SDK
// and react resolve through the acceptance fakes' loader, exactly like the
// shipped bundle under test.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { register } from 'node:module'

// The loader must be live BEFORE the SDK-facing module is imported, so the
// surfaces import is dynamic; the area constants and the expander come from the
// same fakes the loader maps the SDK specifiers to. The fakes are plain .mjs —
// variable specifiers keep tsc from resolving them, and the shapes below are
// every field these tests touch.
register(new URL('../../acceptance/fake/loader.mjs', import.meta.url).href)

interface FakeAreas { leading: string; right: string; top: string; center: string }
interface AreaSets { SESSION_ROW_AREAS: FakeAreas; STATUSBAR_AREAS: FakeAreas; COMPOSER_AREAS: FakeAreas; TITLEBAR_AREAS: FakeAreas }
interface FakeReact { expand(node: unknown, state?: { effects: Array<() => unknown> }): { tree: unknown } }

const sdkPath = '../../acceptance/fake/sdk.mjs'
const reactPath = '../../acceptance/fake/react.mjs'
const { SESSION_ROW_AREAS, STATUSBAR_AREAS, COMPOSER_AREAS, TITLEBAR_AREAS } = await import(sdkPath) as AreaSets
const { expand } = await import(reactPath) as FakeReact
import type { PluginContext } from '@hermes/plugin-sdk'
import { applyFeed, initialView, type CfView } from '../../../src/adapters/view.ts'

const { registerSurfaces } = await import('../../../src/adapters/surfaces.ts')

const view = (): CfView => initialView({ width: 1200, height: 800, ground: '#141416', reducedMotion: false })

interface FakeHost { ctx: PluginContext; contributions: Map<string, Record<string, unknown>>; removed: string[] }

/** A ctx that only records register() and its disposers — the one door registerSurfaces uses. */
function fakeCtx(): FakeHost {
  const contributions = new Map<string, Record<string, unknown>>()
  const removed: string[] = []
  const ctx = {
    register: (x: Record<string, unknown>): (() => void) => {
      contributions.set(String(x.id), x)
      return () => { removed.push(String(x.id)) }
    },
  } as unknown as PluginContext
  return { ctx, contributions, removed }
}

test('surfaces: four contributions at the SDK areas, order 0, disposed together', () => {
  const h = fakeCtx()
  const off = registerSurfaces(h.ctx, view(), () => () => {})
  assert.deepEqual([...h.contributions.entries()].map(([id, c]) => ({ id, area: c.area, order: c.order })), [
    { id: 'swatch', area: SESSION_ROW_AREAS.leading, order: 0 },
    { id: 'strip', area: STATUSBAR_AREAS.right, order: 0 },
    { id: 'rim', area: COMPOSER_AREAS.top, order: 0 },
    { id: 'title', area: TITLEBAR_AREAS.center, order: 0 },
  ])
  off()
  assert.deepEqual([...h.removed].sort(), ['rim', 'strip', 'swatch', 'title'], 'the disposer removes every registration')
})

test('surfaces: the chip speaks the state\'s own words, and says nothing for an unnamed state', () => {
  const h = fakeCtx()
  const v = view()
  applyFeed(v, { kind: 'state', t: 0, session: null, payload: { gateway: 'open', focused_session_id: 'a', focused_stored_session_id: 'SA' } })
  applyFeed(v, { kind: 'plugin.cuttlefish-theme.needs_you', t: 1, session: null,
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r1', kind: 'approval', active: true } })
  registerSurfaces(h.ctx, v, () => () => {})
  const chip = expand((h.contributions.get('strip')!.render as () => unknown)()).tree as { props: { children: unknown[] } }
  assert.equal(chip.props.children[1], v.settings.states[v.focusedState].label, 'the known state\'s label shows')
  assert.notEqual(chip.props.children[1], '', 'and it is words, not silence')
  const ghost = view()
  ghost.focusedState = 'a_state_no_settings_name'
  const h2 = fakeCtx()
  registerSurfaces(h2.ctx, ghost, () => () => {})
  const mute = expand((h2.contributions.get('strip')!.render as () => unknown)()).tree as { props: { children: unknown[] } }
  assert.equal(mute.props.children[1], 'a state no settings name', 'a state with no label falls back to its own name, never a throw')
})

test('surfaces D4: the status strip ALWAYS names the state — a resting (empty-label) strip says "resting", dim', () => {
  const h = fakeCtx()
  const v = view()
  applyFeed(v, { kind: 'state', t: 0, session: null, payload: { gateway: 'open', focused_session_id: 'a', focused_stored_session_id: 'SA' } })
  assert.equal(v.settings.states.resting.label, '', 'the locked default label of resting is empty')
  registerSurfaces(h.ctx, v, () => () => {})
  const chip = expand((h.contributions.get('strip')!.render as () => unknown)()).tree as { props: { children: unknown[] } }
  assert.equal(chip.props.children[1], 'resting')
  const text = JSON.stringify(expand((h.contributions.get('strip')!.render as () => unknown)()).tree)
  assert.ok(text.includes('"resting"'))
})

test('surfaces: the composer rim is one clean 4–6 px full-width band, no words, no grain (legibility)', () => {
  const h = fakeCtx()
  const v = view()
  registerSurfaces(h.ctx, v, () => () => {})
  const rim = expand((h.contributions.get('rim')!.render as () => unknown)()).tree as
    { type: string; props: { style: { height: number; width: string; lineHeight: number; overflow: string; pointerEvents: string }; children: unknown; 'data-cf-state': string; 'data-cf-rim': string } }
  assert.equal(rim.props['data-cf-state'], 'resting')
  assert.equal(rim.props['data-cf-rim'], 'cuttlefish')
  assert.ok(rim.props.style.height >= 4 && rim.props.style.height <= 6, `rim is ${rim.props.style.height}px tall`)
  assert.equal(rim.props.style.width, '100%', 'full width')
  assert.equal(rim.props.style.lineHeight, 0, 'no inline baseline gap can grow the band')
  assert.equal(rim.props.style.overflow, 'hidden')
  assert.equal(rim.props.style.pointerEvents, 'none', 'a decoration never eats a click')
  const kids = ([] as unknown[]).concat(rim.props.children)
  assert.ok(kids.every(k => typeof k === 'object' && k !== null), 'no label text node in the rim')
  const json = JSON.stringify(rim.props.children)
  assert.ok(json.includes('"type":"rect"') && !json.includes('"type":"circle"'), 'a resting rim is a hairline, not dots')
  assert.ok(!json.includes('"type":"pattern"'), 'and not a tiled texture')
  const strip = JSON.stringify(expand((h.contributions.get('strip')!.render as () => unknown)()).tree)
  assert.ok(!strip.includes('"type":"pattern"'), 'the status strip keeps its own look')
})

test('surfaces D3: a swatch re-renders only for its OWN state; the chrome only for the focused one; settings/ground move every key', async () => {
  const { swatchKey, chromeKey } = await import('../../../src/adapters/surfaces.ts')
  const { applyEnv } = await import('../../../src/adapters/view.ts')
  const v = view()
  applyFeed(v, { kind: 'state', t: 0, session: null, payload: { gateway: 'open', focused_session_id: 'a', focused_stored_session_id: 'SA' } })
  applyFeed(v, { kind: 'session.info', t: 1, session: 'b', payload: { stored_session_id: 'SB' } })
  const [a0, b0, c0] = [swatchKey(v, 'SA'), swatchKey(v, 'SB'), chromeKey(v)]
  applyFeed(v, { kind: 'plugin.cuttlefish-theme.needs_you', t: 2, session: null, payload: { session_id: 'SB', request_id: 'r', active: true } })
  assert.equal(swatchKey(v, 'SA'), a0, 'A is unmoved by B')
  assert.notEqual(swatchKey(v, 'SB'), b0, 'B changed')
  assert.equal(chromeKey(v), c0, 'the focused chrome is unmoved by a background session')
  applyFeed(v, { kind: 'plugin.cuttlefish-theme.needs_you', t: 3, session: null, payload: { session_id: 'SA', request_id: 'r2', active: true } })
  assert.notEqual(chromeKey(v), c0, 'the focused session changed state')
  const k = chromeKey(v)
  applyEnv(v, { ground: '#fafafa' })
  assert.notEqual(chromeKey(v), k)
  assert.notEqual(swatchKey(v, 'SB'), b0)
})
