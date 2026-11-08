// Unit contract of the field painter (adapters lane): the ONE owned <style> text follows
// ruling R-S1 (contract/PARTS.md addendum): the field is an svg data-URI layer on
// [data-chat-surface] over the user's own ground BY REFERENCE, and nothing else is declared.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { renderField, toSvg } from '../../../src/domain/index.ts'
import { fieldCss, ringOf } from '../../../src/adapters/painter.ts'
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
  const oracle = (v: CfView, seed: string): string =>
    encodeURIComponent(toSvg(renderField({
      seed, width: v.width, height: v.height, hueDeg: v.hueDeg, ground: v.ground,
      pattern: v.pattern, intensity: v.settings.intensity, motion: v.motion,
      reducedMotion: v.reducedMotion, tMs: v.tMs, sinceChangeMs: v.sinceChangeMs,
    }), v.width, v.height))
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
