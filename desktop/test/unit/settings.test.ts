// Unit: settings resolution edges beyond the contract vectors — silence for null, prototype
// safety, freshness of every resolved copy, and the stateFor/patternOf invariants.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { DEFAULT_SETTINGS, patternOf, resolveSettings, stateFor } from '../../src/domain/settings.ts'

test('null and undefined mean "nothing was given": the defaults, no warnings', () => {
  for (const none of [null, undefined]) {
    const r = resolveSettings(none)
    assert.deepEqual(r.warnings, [])
    assert.deepEqual(r.settings, DEFAULT_SETTINGS)
  }
})

test('every resolveSettings result is a fresh copy: mutating it never touches the defaults', () => {
  const before = JSON.stringify(DEFAULT_SETTINGS)
  const r = resolveSettings({ states: { working: { label: 'busy!' } } })
  r.settings.states.working.label = 'mutated'
  r.settings.patterns.zebra.scale = 99
  assert.equal(JSON.stringify(DEFAULT_SETTINGS), before)
})

test('dangerous key names are skipped everywhere, not read and not warned', () => {
  const r = resolveSettings({
    __proto__: 1,
    states: { __proto__: { when: 'busy', pattern: 'zebra', priority: 500 }, constructor: 3 },
    patterns: { prototype: { base: 'zebra' } },
  })
  assert.ok(!r.warnings.some(w => w.path.includes('proto') || w.path.includes('constructor') || w.path.includes('prototype')))
  assert.equal(({} as Record<string, unknown>).when, undefined, 'the shared prototype must stay clean')
  assert.ok(!Object.prototype.hasOwnProperty.call(r.settings.states, '__proto__'))
  assert.ok(!Object.prototype.hasOwnProperty.call(r.settings.patterns, 'prototype'))
})

test('NaN, Infinity and -Infinity are rejected wherever a number is read', () => {
  const r1 = resolveSettings({ patterns: { zebra: { scale: Number.NaN } } })
  assert.equal(r1.settings.patterns.zebra.scale, 1)
  assert.deepEqual(r1.warnings.map(w => [w.path, w.code]), [['patterns.zebra.scale', 'type']])
  const r2 = resolveSettings({ states: { resting: { priority: Number.POSITIVE_INFINITY } } })
  assert.equal(r2.settings.states.resting.priority, 0)
  assert.deepEqual(r2.warnings.map(w => [w.path, w.code]), [['states.resting.priority', 'type']])
})

test('null removes a STATE silently; a built-in pattern cannot be removed, only warned about', () => {
  const gone = resolveSettings({ states: { working: null } })
  assert.deepEqual(gone.warnings, [])
  assert.equal(gone.settings.states.working, undefined)
  assert.equal(stateFor(gone.settings, new Set(['busy'])), 'resting', 'busy with no busy state falls back to resting')

  const kept = resolveSettings({ patterns: { zebra: null } })
  assert.deepEqual(kept.warnings.map(w => [w.path, w.code]), [['patterns.zebra', 'required']])
  assert.deepEqual(kept.settings.patterns.zebra, DEFAULT_SETTINGS.patterns.zebra)
})

test('stateFor: priorities order, ties break alphabetically, nothing on → resting', () => {
  const s = resolveSettings({
    states: {
      working: null,
      a_tie: { when: 'busy', pattern: 'mottle', priority: 50, label: 'a' },
      b_tie: { when: 'busy', pattern: 'clouds', priority: 50, label: 'b' },
    },
  }).settings
  assert.equal(stateFor(s, new Set(['busy'])), 'a_tie')
  assert.equal(stateFor(s, new Set(['idle'])), 'resting')
  assert.equal(stateFor(s, new Set()), 'resting')
})

test('patternOf returns a copy: tuning it cannot leak into the settings', () => {
  const p = patternOf(DEFAULT_SETTINGS, 'resting')
  p.scale = 4
  assert.equal(DEFAULT_SETTINGS.patterns.mottle.scale, 1)
  assert.throws(() => patternOf(DEFAULT_SETTINGS, 'no_such_state'), /no such state/)
})
