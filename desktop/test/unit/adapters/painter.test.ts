// Unit contract of the field painter (adapters lane): the ONE owned <style> text follows
// ruling R-S1 (contract/PARTS.md addendum): the field is an svg data-URI layer on
// [data-chat-surface] over the user's own ground BY REFERENCE, and nothing else is declared.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { allocate, DEFAULT_SETTINGS, patternOf, renderField, toSvg, type Dot } from '../../../src/domain/index.ts'
import { FIELD_CIRCLES, fieldCss, layerCircles, layerFor, ringOf } from '../../../src/adapters/painter.ts'
import { banding, dotDeltaL } from '../../acceptance/instruments.ts'
import { GROUNDS, PRESETS, ROOTS } from '../../acceptance/corpus.ts'
import { applyFeed, initialView, NO_FOCUS_SEED, type CfView } from '../../../src/adapters/view.ts'

const view = (over: Partial<Parameters<typeof initialView>[0]> = {}): CfView =>
  initialView({ width: 1200, height: 800, ground: '#141416', reducedMotion: false, ...over })

const rules = (css: string) =>
  css.split('}').map(r => r.trim()).filter(Boolean).map(r => r.split('{'))
const declsOf = (css: string, sel: string) => rules(css).find(([s]) => s === sel)?.[1] ?? ''
const layers = (value: string) => value.split(',').map(l => l.trim())
const circles = (css: string): number => {
  const uri = /url\("data:image\/svg\+xml,([^"]*)"\)/.exec(css)?.[1] ?? ''
  return (decodeURIComponent(uri).match(/<circle\b/g) ?? []).length
}

test('painter: the field is the R-S1 route, exactly', () => {
  const css = fieldCss(view())
  assert.match(css, /^\[data-chat-surface\]\{/)
  const surface = declsOf(css, '[data-chat-surface]')
  assert.ok(surface.includes('--ui-chat-surface-background:transparent'), surface)
  assert.ok(/background:url\("data:image\/svg\+xml,/.test(surface), 'the svg layer leads the background')
  const bg = surface.split(';').map(d => d.trim()).find(d => d.startsWith('background:'))!.slice('background:'.length)
  const parts = layers(bg)
  assert.equal(parts.at(-1), 'var(--cf-ground)', 'the last layer is the ground by reference')
  assert.ok(circles(css) >= 40, `${circles(css)} organs: a sparse scatter, not a fill`)
  assert.ok(surface.includes('--dt-composer-ring:#'), 'the composer ring token is set')
  assert.ok(!surface.includes('background-color'), 'the user\'s own ground stays')
  assert.ok(css.includes(':root{--cf-ground:var(--ui-chat-surface-background)}'), 'the ground alias at :root')
})

test('painter: nothing else is declared (the property allowlist of oA_part5)', () => {
  const css = fieldCss(view())
  for (const [sel] of rules(css)) {
    assert.ok(sel === '[data-chat-surface]' || sel === ':root', `selector ${sel}`)
  }
  for (const decl of declsOf(css, ':root').split(';')) {
    assert.ok(decl.startsWith('--'), `:root declares ${decl}`)
  }
  for (const decl of declsOf(css, '[data-chat-surface]').split(';')) {
    const prop = decl.split(':')[0]
    assert.ok(prop.startsWith('--') || prop === 'background', `the surface declares ${decl}`)
  }
})

test('painter: the field scatters on the focused session, or the shared seed with nobody focused', () => {
  // the layer is the 48-circle budget of the same render (v2.1 D3): the oracle applies the same serialisation
  const oracle = (v: CfView, seed: string): string =>
    encodeURIComponent(toSvg(layerCircles(renderField({
      seed, width: v.width, height: v.height, hueDeg: v.hueDeg, ground: v.ground,
      pattern: v.pattern, intensity: v.settings.intensity, motion: v.motion,
      reducedMotion: v.reducedMotion, tMs: v.tMs, sinceChangeMs: v.sinceChangeMs,
    })), v.width, v.height))
  const none = view()
  assert.ok(fieldCss(none).includes(oracle(none, NO_FOCUS_SEED)), 'no focus: the shared seed paints the field')
  const v = view()
  applyFeed(v, working())
  v.tMs = 0; v.sinceChangeMs = 10_000
  const seed = v.focusedStored
  assert.ok(seed !== null, 'the working input focuses a stored session')
  assert.ok(fieldCss(v).includes(oracle(v, seed)), 'focused: the stored id is the seed')
  assert.notEqual(oracle(v, seed), oracle(v, NO_FOCUS_SEED), 'the two seeds paint different fields')
})

test('painter: the ring is the identity hue, never the state', () => {
  const a = view()
  applyFeed(a, { kind: 'state', t: 0, session: null, payload: { gateway: 'open', focused_session_id: 'x', focused_stored_session_id: 'SA' } })
  assert.equal(a.focusedStored, 'SA')
  const rest = ringOf(a.hueDeg, a.ground)
  const cssRest = fieldCss(a)
  applyFeed(a, { kind: 'plugin.cuttlefish-theme.needs_you', t: 1, session: null,
    payload: { session_id: 'SA', session_key: 'SA', request_id: 'r', kind: 'approval', active: true } })
  assert.equal(a.focusedState, 'needs_you')
  assert.equal(ringOf(a.hueDeg, a.ground), rest, 'the hue does not move with the state')
  assert.equal(/--dt-composer-ring:(#[0-9a-f]{6})/.exec(fieldCss(a))![1], /--dt-composer-ring:(#[0-9a-f]{6})/.exec(cssRest)![1])
})

const working = (t = 0) => ({ kind: 'state', t, session: 'a' as string | null,
  payload: { gateway: 'open', busy: true, focused_session_id: 'a', focused_stored_session_id: 'SA' } })

test('painter: working clouds drift between frames, rest does not', () => {
  const v = view()
  applyFeed(v, working())
  v.tMs = 0; v.sinceChangeMs = 10_000
  const f0 = fieldCss(v)
  v.tMs = 1000
  const f1 = fieldCss(v)
  assert.notEqual(f1, f0, 'a second of working moves the passing cloud')
  assert.ok(circles(f1) >= 40, 'the working field keeps its organs')
  const rest = view()
  rest.tMs = 0; rest.sinceChangeMs = 10_000
  const r0 = fieldCss(rest)
  rest.tMs = 5000
  assert.equal(fieldCss(rest), r0, 'the resting mottle is static')
})

test('painter: reduced motion parks the cloud, the bloom passes', () => {
  const v = view({ reducedMotion: true })
  applyFeed(v, working())
  v.tMs = 0; v.sinceChangeMs = 0
  const b0 = fieldCss(v)
  v.tMs = 1000
  assert.equal(fieldCss(v), b0, 'prefers-reduced-motion: no drift while working')
  const w = view()
  applyFeed(w, working())
  w.tMs = 0; w.sinceChangeMs = 300
  const bloom = fieldCss(w)
  w.sinceChangeMs = 10_000
  assert.notEqual(fieldCss(w), bloom, 'the bloom settles')
})

test('painter D3: the frame memo keys on EVERY input — changing any one of them changes the text', () => {
  const base = view()
  applyFeed(base, { kind: 'state', t: 0, session: 'a', payload: { gateway: 'open', busyBySession: { a: true }, focused_session_id: 'a', focused_stored_session_id: 'SA' } })
  base.sinceChangeMs = 1e9
  base.tMs = 3000
  const css0 = fieldCss(base)
  assert.equal(fieldCss({ ...base }), css0, 'the same inputs, the same text')
  const variants: Record<string, Partial<CfView>> = {
    stored: { focusedStored: 'SB' }, width: { width: 1300 }, height: { height: 700 }, hue: { hueDeg: (base.hueDeg + 40) % 360 },
    ground: { ground: '#fafafa' }, tMs: { tMs: 6000 }, since: { sinceChangeMs: 100 }, motion: { motion: 'alive' },
    reduced: { reducedMotion: true }, pattern: { pattern: { ...base.pattern, base: 'zebra' } },
    intensity: { settings: { ...base.settings, intensity: 0.5 } },
  }
  for (const [name, over] of Object.entries(variants)) {
    assert.notEqual(fieldCss({ ...base, ...over }), css0, `${name} is part of the key`)
  }
})

test('painter D3 (v2.1): the field layer is at most 48 circles, at least 40, the highest-alpha organs, and it always keeps the eye-spot', () => {
  const render = (preset: string): Dot[] => renderField({
    seed: 'budget-seed', width: 1200, height: 800, hueDeg: allocate('budget-seed', []).hue_deg, ground: '#141416',
    pattern: patternOf(DEFAULT_SETTINGS, preset), intensity: 1, motion: 'still', reducedMotion: false, tMs: 0, sinceChangeMs: 10_000,
  })
  assert.equal(FIELD_CIRCLES, 48)
  const working = render('working')
  const kept = layerCircles(working)
  assert.equal(kept.length, FIELD_CIRCLES, 'a busy field is cut to the budget')
  const dropped = working.filter(d => d.alpha > 0 && d.r > 0 && !kept.includes(d))
  assert.ok(Math.min(...kept.map(d => d.alpha)) >= Math.max(...dropped.map(d => d.alpha)), 'the cut keeps the highest-alpha circles')
  const eye = layerCircles(render('finished_unseen'))
  assert.ok(eye.some(d => d.role === 'eyespot'), 'the eye-spot survives the cut at any rank')
  assert.ok(eye.length >= 40, `at least 40 circles (${eye.length})`)
})

// v2.1 round 4 (§4b F-A): the 48-circle budget is for the clouds only. A static field draws every organ, because the
// stripes read the dim off-band organs (deleting them made needs_you highK 0.28 on the real Desktop; the floor is 0.6).
const surfaceOf = (base: string, root: string, ground: string, w: number, h: number, preset = base): Dot[] => renderField({
  seed: root, width: w, height: h, hueDeg: allocate(root, []).hue_deg, ground,
  pattern: patternOf(DEFAULT_SETTINGS, preset), intensity: 1, motion: 'still', reducedMotion: false, tMs: 0, sinceChangeMs: 10_000,
})

test('the circle budget is for the clouds only: a static field keeps every visible organ, the dim ones included', () => {
  const dots = surfaceOf('zebra', ROOTS[0], GROUNDS[0], 1600, 1000, 'needs_you')
  const visible = dots.filter(d => d.alpha > 0 && d.r > 0)
  const layer = layerFor('zebra', dots)
  assert.equal(layer.length, visible.length, 'needs_you keeps every organ')
  assert.ok(layer.length >= 90, `needs_you at 1600×1000: ${layer.length} circles`)
  assert.ok(layer.filter(d => dotDeltaL(d, GROUNDS[0]) < 0.03).length >= 30, 'and the dim off-band organs among them')
  assert.equal(layerFor('clouds', surfaceOf('clouds', ROOTS[0], GROUNDS[0], 1600, 1000, 'working')).length, FIELD_CIRCLES,
    'the clouds, which repaint, keep the budget')
})

test('the shipped layer keeps the stripes: needs_you highK ≥ 0.6 by the domain classifier, every root and ground, at 1600×1000', () => {
  for (const root of ROOTS) for (const ground of GROUNDS) {
    const b = banding(layerFor('zebra', surfaceOf('zebra', root, ground, 1600, 1000, 'needs_you')), ground, 1600, 1000)
    assert.ok(b.highK >= 0.6, `${root} ${ground}: needs_you highK ${b.highK.toFixed(2)}`)
  }
})

test('after culling every state keeps between 40 and 190 organ circles (every preset, three sizes)', () => {
  const base: Record<string, string> = { resting: 'mottle', working: 'clouds', needs_you: 'zebra', error: 'blanch', finished_unseen: 'eyespot' }
  for (const preset of PRESETS) for (const root of ROOTS.slice(0, 4)) for (const [w, h] of [[1600, 1000], [1200, 800], [1339, 879]]) {
    const dots = surfaceOf(base[preset], root, GROUNDS[0], w, h, preset)
    const layer = layerFor(base[preset], dots)
    const organs = layer.filter(d => d.role === 'organ').length
    assert.ok(organs >= 40, `${preset} ${root} ${w}×${h}: ${organs} organs`)
    assert.ok(layer.length <= 190, `${preset} ${root} ${w}×${h}: ${layer.length} circles`)
  }
})
