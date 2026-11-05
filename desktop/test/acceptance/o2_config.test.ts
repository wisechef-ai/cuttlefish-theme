// ACCEPTANCE CONTRACT — O2 vocabulary: users remap and extend the language through config only (locked).
// SPEC C2/C5. Ceiling ↔ floor: every bad input is REJECTED with a named warning AND every good remap is HONOURED.
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}

const VEC = JSON.parse(readFileSync(new URL('../../../contract/config-vectors.json', import.meta.url), 'utf8'))

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function subset(actual: any, expected: any, path: string): void {
  if (expected !== null && typeof expected === 'object' && !Array.isArray(expected)) {
    assert.ok(actual && typeof actual === 'object', `${path}: expected a mapping, got ${JSON.stringify(actual)}`)
    for (const k of Object.keys(expected)) subset(actual[k], expected[k], `${path}.${k}`)
  } else {
    assert.deepEqual(actual, expected, path)
  }
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const dig = (o: any, dotted: string) => dotted.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o)

test('O2c.1 DEFAULT_SETTINGS are exactly the five presets of the spec', () => {
  assert.deepEqual(D().DEFAULT_SETTINGS, VEC.defaults)
})

for (const c of VEC.cases) {
  test(`O2c vector: ${c.name}`, () => {
    const { settings, warnings } = D().resolveSettings(c.input)
    subset(settings, c.expect, 'settings')
    if (c.exact_defaults) assert.deepEqual(settings, VEC.defaults)
    for (const a of c.absent ?? []) assert.equal(dig(settings, a), undefined, `${a} should have been dropped`)
    const got = warnings.map((w: { path: string; code: string }) => [w.path, w.code]).sort()
    assert.deepEqual(got, [...c.warnings].sort(), `warnings for ${JSON.stringify(c.input)}`)
    for (const w of warnings) assert.ok(typeof w.message === 'string' && w.message.length > 0, 'a warning says what is wrong')
  })
}

test('O2c.2 non-finite numbers are rejected wherever a number is read', () => {
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const r1 = D().resolveSettings({ intensity: bad })
    assert.equal(r1.settings.intensity, 1)
    assert.equal(r1.warnings.length, 1)
    const r2 = D().resolveSettings({ patterns: { p: { base: 'zebra', contrast: bad } } })
    assert.equal(r2.settings.patterns.p.contrast, 1)
    const r3 = D().resolveSettings({ states: { working: { priority: bad } } })
    assert.equal(r3.settings.states.working.priority, 60)
  }
})

test('O2c.3 resolveSettings never throws and never mutates its input', () => {
  const weird: unknown[] = [undefined, 0, -0, 'x', [], [{}], { states: { __proto__: { evil: 1 } } }, { states: { constructor: { when: 'busy', pattern: 'zebra', priority: 1 } } }]
  for (const w of weird) {
    const before = JSON.stringify(w)
    assert.doesNotThrow(() => D().resolveSettings(w))
    assert.equal(JSON.stringify(w), before)
  }
  const polluted = D().resolveSettings(JSON.parse('{"states":{"__proto__":{"when":"busy","pattern":"zebra","priority":1}}}'))
  assert.equal(({} as Record<string, unknown>).when, undefined, 'prototype pollution')
  assert.ok(!Object.prototype.hasOwnProperty.call(polluted.settings.states, '__proto__'))
})

const sig = (...s: string[]) => new Set(s)

test('O2c.4 stateFor: highest priority wins; idle always counts; ties break by name; none → resting', () => {
  const s = D().DEFAULT_SETTINGS
  assert.equal(D().stateFor(s, sig()), 'resting')
  assert.equal(D().stateFor(s, sig('idle')), 'resting')
  assert.equal(D().stateFor(s, sig('busy')), 'working')
  assert.equal(D().stateFor(s, sig('busy', 'needs_input')), 'needs_you')
  assert.equal(D().stateFor(s, sig('busy', 'failed')), 'error')
  assert.equal(D().stateFor(s, sig('failed', 'needs_input')), 'needs_you')
  assert.equal(D().stateFor(s, sig('unseen')), 'finished_unseen')
  assert.equal(D().stateFor(s, sig('unseen', 'busy')), 'working')
  assert.equal(D().stateFor(s, sig('compacting', 'tool', 'offline')), 'resting', 'unbound signals fall through')
  const custom = D().resolveSettings({ states: { compacting: { when: 'compacting', pattern: 'zebra', priority: 70 },
    alpha: { when: 'tool', pattern: 'mottle', priority: 70 }, beta: { when: 'tool', pattern: 'zebra', priority: 70 } } }).settings
  assert.equal(D().stateFor(custom, sig('busy', 'compacting')), 'compacting')
  assert.equal(D().stateFor(custom, sig('tool')), 'alpha', 'equal priority: alphabetical')
  const noWorking = D().resolveSettings({ states: { working: null } }).settings
  assert.equal(D().stateFor(noWorking, sig('busy')), 'resting', 'a removed preset no longer matches')
})

test('O2c.5 patternOf resolves names, including a user pattern, and remaps change what renders', () => {
  const s = D().resolveSettings({ patterns: { dense: { base: 'mottle', density: 2 } },
    states: { needs_you: { pattern: 'dense' }, working: { pattern: 'zebra' } } }).settings
  assert.deepEqual(D().patternOf(s, 'needs_you'), { base: 'mottle', density: 2, contrast: 1, scale: 1 })
  assert.equal(D().patternOf(s, 'working').base, 'zebra')
  assert.equal(D().patternOf(D().DEFAULT_SETTINGS, 'finished_unseen').base, 'eyespot')
  assert.throws(() => D().patternOf(s, 'no-such-state'))
})
