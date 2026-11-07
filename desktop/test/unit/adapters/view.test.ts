// Unit contract of the adapter view-model (adapters lane): what the surfaces read — the
// focused session's state through the domain, the identity hue, change detection keyed on
// the STATE NAME (a focus switch alone never blooms), live settings, and the subscribe
// channel the React surfaces ride.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { allocate, DEFAULT_SETTINGS, resolveSettings } from '../../../src/domain/index.ts'
import { applyEnv, applyFeed, applySettings, initialView, NO_FOCUS_SEED, safePattern } from '../../../src/adapters/view.ts'

const v = () => initialView({ width: 1200, height: 800, ground: '#141416', reducedMotion: false })
const focusSA = (x = 0) => ({ kind: 'state', t: x, session: null as string | null,
  payload: { gateway: 'open', focused_session_id: 'a', focused_stored_session_id: 'SA' } })
const needsYou = (id = 'SA') => ({ kind: 'plugin.cuttlefish-theme.needs_you', t: 1, session: null as string | null,
  payload: { session_id: id, session_key: id, request_id: 'r1', kind: 'approval', active: true } })

test('view: initial sight is resting, unblloomed, with the fallback seed', () => {
  const s = v()
  assert.equal(s.focusedStored, null)
  assert.equal(s.focusedState, 'resting')
  assert.equal(s.hueDeg, allocate(NO_FOCUS_SEED, []).hue_deg)
  assert.deepEqual(s.pattern, DEFAULT_SETTINGS.patterns.mottle)
  assert.equal(s.version, 1)
})

test('view: the first focus is not a change; only a state move blooms', () => {
  const s = v()
  assert.equal(applyFeed(s, focusSA()), false, 'focus alone never blooms')
  assert.equal(s.focusedStored, 'SA')
  assert.equal(s.focusedState, 'resting')
  assert.equal(applyFeed(s, { kind: 'state', t: 2, session: 'a', payload: { gateway: 'open', busy: true, busyBySession: { a: true } } }), true, 'working blooms')
  assert.equal(s.focusedState, 'working')
  assert.equal(applyFeed(s, needsYou()), true)
  assert.equal(s.focusedState, 'needs_you')
})

test('view: a focus switch between equal states does not bloom', () => {
  const s = v()
  applyFeed(s, focusSA())
  applyFeed(s, { kind: 'state', t: 2, session: 'a', payload: { gateway: 'open', busy: true, busyBySession: { a: true } } })
  const hueA = s.hueDeg
  assert.equal(applyFeed(s, { kind: 'state', t: 3, session: 'b', payload: { gateway: 'open', busy: true, focused_session_id: 'b', focused_stored_session_id: 'SB', busyBySession: { b: true } } }), false)
  assert.equal(s.focusedStored, 'SB')
  assert.equal(s.focusedState, 'working')
  assert.notEqual(s.hueDeg, hueA, 'the identity follows the focused session')
})

test('view: settings apply in place — motion, patterns, user states', () => {
  const s = v()
  applyFeed(s, focusSA())
  const raw = { states: { compacting_seen: { when: 'compacting', pattern: 'ripple', priority: 70, label: 'tidying up' } },
    patterns: { ripple: { base: 'clouds', density: 2, contrast: 1.5, scale: 1 } }, motion: 'alive' }
  applySettings(s, resolveSettings(raw).settings)
  assert.equal(s.motion, 'alive')
  assert.deepEqual(safePattern(s.settings, 'compacting_seen'), { base: 'clouds', density: 2, contrast: 1.5, scale: 1 })
  applyFeed(s, { kind: 'status.update', t: 4, session: 'a', payload: { kind: 'compacting' } })
  assert.equal(s.focusedState, 'compacting_seen', 'a user state reaches the view end to end')
  applySettings(s, DEFAULT_SETTINGS)
  assert.equal(s.focusedState, 'resting', 'removing the addition falls through to resting')
})

test('view: env patches repaint inputs without touching the feed', () => {
  const s = v()
  applyEnv(s, { ground: '#fbfbfa', width: 800, height: 600, reducedMotion: true })
  assert.equal(s.ground, '#fbfbfa')
  assert.equal(s.width, 800)
  assert.equal(s.reducedMotion, true)
  assert.equal(s.feed.gateway, null)
})

test('view: subscribers hear every apply; unsubscribe stops', () => {
  const s = v()
  const seen: number[] = []
  const off = s.listen(() => seen.push(s.version))
  applyFeed(s, focusSA())
  applyEnv(s, { reducedMotion: true })
  off()
  const after = seen.length
  applyEnv(s, { reducedMotion: false })
  assert.equal(seen.length, after, 'unsubscribed')
  assert.deepEqual([...new Set(seen)], seen, 'one bump per apply')
})
