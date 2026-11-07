// Review round (reviews/review-domain-js.md F1-F4): behaviours the first build got wrong or never pinned.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { GROUNDS, H, PRESETS, ROOTS, W } from '../acceptance/corpus.ts'
import { hexToRgb, rgbToOklab } from '../acceptance/instruments.ts'
import {
  allocate, DEFAULT_SETTINGS, initialFeed, patternOf, reduceFeed, renderField, resolveSettings, signalsOf,
} from '../../src/domain/index.ts'

const NAMES = ['__proto__', 'constructor', 'prototype', 'toString', 'valueOf', 'hasOwnProperty', 'isPrototypeOf']

const field = (over: Record<string, unknown>) => renderField({
  seed: ROOTS[0], width: W, height: H, hueDeg: 200, ground: GROUNDS[0], pattern: patternOf(DEFAULT_SETTINGS, 'resting'),
  intensity: 1, motion: 'alive', reducedMotion: false, tMs: 0, sinceChangeMs: 99999, ...over,
} as never)

test('F1 reduced motion freezes the render: alive + reducedMotion is time-independent (control: alive alone twinkles)', () => {
  for (const p of PRESETS) {
    const pattern = patternOf(DEFAULT_SETTINGS, p)
    const at = (tMs: number, reducedMotion: boolean) => JSON.stringify(field({ pattern, tMs, reducedMotion }))
    assert.equal(at(0, true), at(3000, true), `${p}: reduced motion must not animate`)
    assert.equal(at(0, true), at(777, true))
  }
  const a = JSON.stringify(field({ tMs: 0 })), b = JSON.stringify(field({ tMs: 3000 }))
  assert.notEqual(a, b, 'control: alive without reduced motion still twinkles')
})

test('F2 prototype-named event kinds, runtime ids and stored ids are ignored or handled as plain ids, never thrown', () => {
  const base = initialFeed()
  for (const k of NAMES) {
    assert.deepEqual(reduceFeed(base, { kind: k, t: 1, payload: {} }), base, `kind ${k} must be an unknown kind`)
    const evs = [
      { kind: 'plugin.cuttlefish-theme.needs_you', t: 1, payload: { session_id: k, request_id: 'r', active: true } },
      { kind: 'plugin.cuttlefish-theme.error', t: 1, payload: { session_id: k, retryable: false } },
      { kind: 'state', t: 1, session: k, payload: { stored_session_id: 's', busy: true } },
      { kind: 'message.start', t: 1, session: k, payload: {} },
      { kind: 'message.complete', t: 1, session: k, payload: { status: 'complete' } },
      { kind: 'tool.start', t: 1, session: k, payload: { tool_call_id: 'a' } },
      { kind: 'subagent.start', t: 1, session: k, payload: {} },
      { kind: 'active_list', t: 1, payload: { sessions: [{ id: k, session_key: k, status: 'waiting' }] } },
    ]
    let m = base
    for (const e of evs) assert.doesNotThrow(() => { m = reduceFeed(m, e) }, `${k}: ${e.kind}`)
    assert.doesNotThrow(() => signalsOf(m, k))
    assert.equal(typeof m, 'object')
  }
  // a fresh, unrelated prototype-named stored id has no signals but idle
  assert.deepEqual([...signalsOf(base, 'toString')], [])
})

test('F3 a state may not point at an inherited name; patternOf then cannot throw for any resolved state', () => {
  for (const k of NAMES) {
    const r = resolveSettings({ states: { x: { when: 'busy', pattern: k, priority: 3 }, resting: { pattern: k } } })
    assert.ok(r.warnings.some(w => w.code === 'unknown' && w.path.endsWith('pattern')), `${k}: no unknown-pattern warning`)
    assert.equal(r.settings.states.x, undefined, `${k}: state with an undefined pattern must be dropped`)
    assert.equal(r.settings.states.resting.pattern, DEFAULT_SETTINGS.states.resting.pattern)
    for (const s of Object.keys(r.settings.states)) assert.doesNotThrow(() => patternOf(r.settings, s), `${k}/${s}`)
    // a state NAMED like a prototype member is a new state (needs its own fields), not a phantom preset
    const n = resolveSettings({ states: { [k]: { when: 'busy', pattern: 'clouds' } } })
    if (k !== '__proto__' && k !== 'constructor' && k !== 'prototype') {
      assert.equal(Object.hasOwn(n.settings.states, k), false, `${k}: a new state without priority is dropped`)
      assert.ok(n.warnings.some(w => w.path === `states.${k}.priority`), `${k}: priority missing warning`)
    }
    const pat = resolveSettings({ patterns: { [k]: { density: 0.5 } } })
    if (!['__proto__', 'constructor', 'prototype'].includes(k)) assert.ok(pat.warnings.some(w => w.path === `patterns.${k}.base`), `${k}: new pattern needs a base`)
  }
})

test('F4 hue is identity: no state changes the pigment hue of any organ (every preset, 3 grounds, 20 roots)', () => {
  const hueOf = (hex: string): number => { const l = rgbToOklab(hexToRgb(hex)); return (Math.atan2(l.b, l.a) * 180 / Math.PI + 360) % 360 }
  // An 8-bit pigment this dark (the ocellus on a dark ground, L ~ 0.03) or this grey has no measurable hue:
  // one RGB step moves its OKLab hue by >10 deg. Everything else must hold the identity hue.
  const measurable = (hex: string): boolean => { const l = rgbToOklab(hexToRgb(hex)); return Math.hypot(l.a, l.b) >= 0.012 && l.L >= 0.1 }
  for (const root of ROOTS) {
    const hue = allocate(root, []).hue_deg
    for (const ground of GROUNDS) for (const p of PRESETS) {
      for (const d of field({ seed: root, hueDeg: hue, ground, pattern: patternOf(DEFAULT_SETTINGS, p), motion: 'still' })) {
        if (!measurable(d.color)) continue
        let diff = Math.abs(hueOf(d.color) - hue); diff = Math.min(diff, 360 - diff)
        assert.ok(diff < 6, `${root}/${ground}/${p}/${d.role}: pigment hue ${hueOf(d.color).toFixed(1)} vs identity ${hue.toFixed(1)}`)
      }
    }
  }
})

import { bloomFactor, BLOOM_MS } from '../../src/domain/index.ts'
test('F6 the bloom envelope is continuous (no step at the open->close hand-over) and still peaks >= 1.5x', () => {
  let prev = bloomFactor(0, 'still', false), peak = prev
  for (let t = 1; t <= BLOOM_MS; t++) {
    const v = bloomFactor(t, 'still', false)
    assert.ok(Math.abs(v - prev) < 0.02, `step ${(v - prev).toFixed(3)} at ${t} ms`)
    peak = Math.max(peak, v); prev = v
  }
  assert.ok(peak >= 1.5)
  assert.ok(bloomFactor(BLOOM_MS - 1, 'still', false) < 1.03, 'settles by the end of the bloom')
})
