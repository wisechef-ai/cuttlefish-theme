// Unit: mutation pins. Each test here kills a specific surviving mutant of the ub-mode
// mutator run: behaviours that were true of the domain but that no earlier test could
// DISTINGUISH from a near-miss — exact stream values, exact range boundaries, tie-break
// order, junk-key purity, buffer caps, and one golden digest of a whole field render
// (the domain promises bit-identical determinism, so any render-path change is a bug).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { blake2b, seededStream, utf8 } from '../../src/domain/blake2b.ts'
import { initialFeed, knownSessions, reduceFeed, signalsOf, type FeedInput } from '../../src/domain/feed.ts'
import { allocate, DEFAULT_SETTINGS, hueDistance, hueOfSlot, patternOf, renderField, renderStrip, renderSwatch, resolveSettings, stateFor, toSvg } from '../../src/domain/index.ts'
import { BLOOM_MS, motionPlan } from '../../src/domain/motion.ts'
import { effectiveDl } from '../../src/domain/pattern.ts'
import { GROUNDS, H, ROOTS, SETTLED_MS, W } from '../acceptance/corpus.ts'

const ev = (kind: string, session: string | null, payload: Record<string, unknown> | null, t = 0): FeedInput =>
  ({ kind, t, session, payload })

test('seededStream: the first eight draws are pinned exactly (the reproducibility contract)', () => {
  const next = seededStream('cuttlefish-test-seed', 'cloud-ink')
  const draws: number[] = []
  for (let i = 0; i < 8; i++) draws.push(next())
  assert.deepEqual(draws.map(d => d.toFixed(9)), [
    '0.082596206', '0.350804601', '0.152384750', '0.545330347',
    '0.396200533', '0.072732081', '0.360761559', '0.855772481',
  ])
})

test('the unmapped-runtime buffer is capped at exactly 64 buffered events', () => {
  let m = initialFeed()
  for (let i = 0; i < 70; i++) m = reduceFeed(m, ev('message.complete', 'rt-x', {}, i))
  assert.equal((m.buffered['rt-x'] ?? []).length, 64)
})

test('status.update raises compacting only for kind "compacting"', () => {
  let m = initialFeed()
  m = reduceFeed(m, ev('state', 'rt-1', { gateway: 'open' }))
  m = reduceFeed(m, ev('session.info', 'rt-1', { stored_session_id: 's1' }))
  m = reduceFeed(m, ev('status.update', 'rt-1', { kind: 'other' }))
  assert.ok(!signalsOf(m, 's1').has('compacting'))
  m = reduceFeed(m, ev('status.update', 'rt-1', { kind: 'compacting' }))
  assert.ok(signalsOf(m, 's1').has('compacting'))
})

test('a busy snapshot without a session id leaves no junk keys behind', () => {
  let m = initialFeed()
  m = reduceFeed(m, ev('state', 'rt-1', { gateway: 'open' }))
  m = reduceFeed(m, ev('state', null, { gateway: 'open', busy: true }))
  assert.deepEqual(knownSessions(m), [])
  assert.deepEqual(Object.keys(m.busyRt), [])
})

test('needs_you: resolving one of two open requests keeps the other open', () => {
  let m = initialFeed()
  m = reduceFeed(m, ev('state', 'rt-1', { gateway: 'open' }))
  for (const q of ['q1', 'q2']) m = reduceFeed(m, ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: q, active: true }))
  m = reduceFeed(m, ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: 'q2', active: false }))
  assert.ok(signalsOf(m, 's1').has('needs_input'), 'q1 must survive q2 resolving')
  m = reduceFeed(m, ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: 'q1', active: false }))
  assert.ok(!signalsOf(m, 's1').has('needs_input'))
})

test('range endpoints are inclusive: intensity 2 and a 24-char label are accepted', () => {
  const a = resolveSettings({ intensity: 2 })
  assert.equal(a.settings.intensity, 2)
  assert.equal(a.warnings.filter(w => w.path === 'intensity').length, 0)
  const b = resolveSettings({ states: { working: { label: 'x'.repeat(24) } } })
  assert.equal(b.settings.states.working.label, 'x'.repeat(24))
  assert.equal(b.warnings.filter(w => w.path === 'states.working.label').length, 0)
  const c = resolveSettings({ states: { working: { label: 'x'.repeat(25) } } })
  assert.equal(c.settings.states.working.label, 'working')
  assert.ok(c.warnings.some(w => w.path === 'states.working.label' && w.code === 'range'))
})

test('a partial preset keeps its own defaults: resting keeps the empty label, working keeps its pattern', () => {
  const a = resolveSettings({ states: { resting: { when: 'idle' } } })
  assert.equal(a.settings.states.resting.label, '')
  const b = resolveSettings({ states: { working: {} } })
  assert.equal(b.settings.states.working.pattern, 'clouds')
  assert.equal(b.settings.states.working.priority, 60)
})

test('a new state with a junk priority is dropped whole; a preset keeps its own', () => {
  const a = resolveSettings({ states: { night: { when: 'idle', pattern: 'mottle', priority: 'junk' } } })
  assert.equal(a.settings.states.night, undefined, 'a new state with a bad priority dies')
  assert.ok(a.warnings.some(w => w.path === 'states.night.priority'))
  const b = resolveSettings({ states: { working: { priority: 'junk' } } })
  assert.equal(b.settings.states.working.priority, 60, 'a preset keeps its own priority')
})

test('stateFor breaks priority ties alphabetically regardless of definition order', () => {
  const s = resolveSettings({
    states: {
      zz_first: { when: 'busy', pattern: 'mottle', priority: 500, label: '' },
      aa_second: { when: 'busy', pattern: 'zebra', priority: 500, label: '' },
    },
  }).settings
  assert.equal(stateFor(s, new Set(['busy'])), 'aa_second')
})

test('motionPlan: the bloom is over at exactly BLOOM_MS, and the settled plan carries fps 0', () => {
  assert.deepEqual(motionPlan({ pattern: 'mottle', motion: 'still', reducedMotion: false, sinceChangeMs: BLOOM_MS }), { animate: false, fps: 0 })
  assert.deepEqual(motionPlan({ pattern: 'mottle', motion: 'still', reducedMotion: false, sinceChangeMs: BLOOM_MS - 1 }), { animate: true, fps: 5 })
  assert.deepEqual(motionPlan({ pattern: 'clouds', motion: 'still', reducedMotion: false, sinceChangeMs: 10_000 }), { animate: true, fps: 8 })
})

test('hueDistance is the shortest angular distance, in either direction', () => {
  assert.equal(hueDistance(350, 10), 20)
  assert.equal(hueDistance(10, 350), 20)
  assert.equal(hueDistance(180, 0), 180)
  assert.equal(hueDistance(110, 340), 130)
})

test('hueOfSlot names the exact legal range in its rejection', () => {
  assert.throws(() => hueOfSlot(20), /0\.\.19/)
})

test('swatch and strip radii are exactly their tuned deterministic ranges; toSvg draws exactly the visible dots', () => {
  const hue = allocate(ROOTS[0], []).hue_deg
  const radii = (dots: { r: number; alpha: number }[]): number[] =>
    dots.filter(d => d.alpha > 0).map(d => d.r).sort((a, b) => a - b)
  const sw = radii(renderSwatch({ seed: ROOTS[0], hueDeg: hue, ground: GROUNDS[0], pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1 }).dots)
  assert.equal(sw[0].toFixed(3), '1.371')
  assert.equal(sw[sw.length - 1].toFixed(3), '1.901')
  const st = radii(renderStrip({ seed: ROOTS[0], hueDeg: hue, ground: GROUNDS[0], pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1 }).dots)
  assert.equal(st[0].toFixed(3), '1.602')
  assert.equal(st[st.length - 1].toFixed(3), '2.247')
  const strip = renderStrip({ seed: ROOTS[0], hueDeg: hue, ground: GROUNDS[0], pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1 })
  const visible = strip.dots.filter(d => d.alpha > 0 && d.r > 0)
  assert.equal((toSvg(strip.dots, strip.width, strip.height).match(/<circle\b/g) ?? []).length, visible.length)
})

test('renderField golden digest: one settled render, bit-identical forever', () => {
  const input = {
    seed: ROOTS[0], width: W, height: H, hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0],
    pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1,
    motion: 'still' as const, reducedMotion: false, tMs: 0, sinceChangeMs: SETTLED_MS,
  }
  assert.equal(input.hueDeg > 110 && input.hueDeg < 340, true)
  const digest = Buffer.from(blake2b(utf8(JSON.stringify(renderField(input))), 32)).toString('hex')
  assert.equal(digest, '2f2dd28c53b35958f45e4c07838e8c6e75c7e953d33fed86e006c53314d0ecdd')
})

// Round-2 pins. The first golden digest ran with every dial at 1 (intensity 1, settled bloom 1,
// still twinkle 1), so `*` vs `/` among those factors was invisible, and nothing pinned the
// small-canvas ink or toSvg's visibility predicate at all. These close those gaps.

test('needs_you: after one of two requests resolves, the record holds exactly the other id', () => {
  let m = initialFeed()
  m = reduceFeed(m, ev('state', 'rt-1', { gateway: 'open' }))
  for (const q of ['q1', 'q2']) m = reduceFeed(m, ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: q, active: true }))
  m = reduceFeed(m, ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: 'q2', active: false }))
  assert.deepEqual(m.sessions['s1']?.needsYou, ['q1'], 'q1 alone survives q2 resolving')
})

test('focus: a runtime id resolves through storedOf, and snapshots without focus fields leave focus untouched', () => {
  let m = initialFeed()
  for (const [rt, s] of [['rt-1', 's1'], ['rt-2', 's2']] as const) {
    m = reduceFeed(m, ev('state', rt, { gateway: 'open' }))
    m = reduceFeed(m, ev('session.info', rt, { stored_session_id: s }))
  }
  m = reduceFeed(m, ev('state', 'rt-2', { gateway: 'open', focused_stored_session_id: 's2', focused_session_id: 'rt-2' }))
  assert.equal(m.focusedStored, 's2')
  // a bare state snapshot carries no focus fields: focus must not move and no junk key may appear
  m = reduceFeed(m, ev('state', 'rt-2', { gateway: 'open' }))
  assert.equal(m.focusedStored, 's2')
  assert.deepEqual(Object.keys(m.sessions).sort(), ['s1', 's2'])
  // runtime focus id alone resolves through the learned mapping
  m = reduceFeed(m, ev('state', 'rt-2', { gateway: 'open', focused_session_id: 'rt-1' }))
  assert.equal(m.focusedStored, 's1')
  // dangerous stored id + unmapped runtime id: unresolvable, so focus holds
  m = reduceFeed(m, ev('state', 'rt-2', { gateway: 'open', focused_stored_session_id: '__proto__', focused_session_id: 'rt-x' }))
  assert.equal(m.focusedStored, 's1')
  assert.deepEqual(Object.keys(m.sessions).sort(), ['s1', 's2'])
})

test('active_list: an entry with a dangerous id creates no session at all', () => {
  let m = initialFeed()
  m = reduceFeed(m, ev('state', 'rt-1', { gateway: 'open' }))
  m = reduceFeed(m, ev('active_list', null, { sessions: [{ id: 'rt-9', session_key: 's9', status: 'running' }] }))
  assert.deepEqual(knownSessions(m), ['s9'])
  m = reduceFeed(m, ev('active_list', null, { sessions: [{ id: '__proto__', session_key: 's99', status: 'running' }] }))
  assert.deepEqual(knownSessions(m), ['s9'], 'a dangerous runtime id disqualifies the whole entry')
})

test('toSvg draws exactly the dots with alpha > 0 and r > 0 — down to r = 0.5', () => {
  const dot = (r: number, alpha: number) => ({ x: 1, y: 1, r, color: '#102030', alpha, role: 'organ' as const })
  const svg = toSvg([dot(1, 1), dot(0.5, 1), dot(5, 0), dot(0, 1), dot(3, 0.5)], 10, 10)
  const rs = [...svg.matchAll(/r="([^"]+)"/g)].map(m2 => m2[1])
  assert.deepEqual(rs.sort(), ['0.5', '1', '3'], 'r=1 and r=0.5 draw; alpha=0 and r=0 do not')
})

test('effectiveDl multiplies its dials: 0.1 × 2 × 0.5 × 0.8 = 0.08', () => {
  assert.ok(Math.abs(effectiveDl(0.1, 2, 0.5, 0.8) - 0.08) < 1e-9)
})

test('renderField golden digest: zebra at scale 2 (the band count follows the dial)', () => {
  const wide = resolveSettings({
    patterns: { wide_zebra: { base: 'zebra', scale: 2 } },
    states: { zb: { when: 'busy', pattern: 'wide_zebra', priority: 10, label: '' } },
  })
  assert.deepEqual(wide.warnings, [])
  const input = {
    seed: ROOTS[0], width: W, height: H, hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0],
    pattern: patternOf(wide.settings, 'zb'), intensity: 1,
    motion: 'still' as const, reducedMotion: false, tMs: 0, sinceChangeMs: SETTLED_MS,
  }
  assert.equal(Buffer.from(blake2b(utf8(JSON.stringify(renderField(input))), 32)).toString('hex'),
    '596599d77c26398bacc47fd7eb97e9ce3e3e75caa5f083b4d9b186772d409162')
})

test('renderField golden digest: resting mottle, settled', () => {
  const input = {
    seed: ROOTS[0], width: W, height: H, hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0],
    pattern: patternOf(DEFAULT_SETTINGS, 'resting'), intensity: 1,
    motion: 'still' as const, reducedMotion: false, tMs: 0, sinceChangeMs: SETTLED_MS,
  }
  assert.equal(Buffer.from(blake2b(utf8(JSON.stringify(renderField(input))), 32)).toString('hex'),
    '00891c930d7ee9f6535561f62fcbcde317a176e332633e619632838b3200b66f')
})

test('renderField golden digest: alive clouds with every dial off unity', () => {
  const input = {
    seed: ROOTS[0], width: W, height: H, hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0],
    pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1.7,
    motion: 'alive' as const, reducedMotion: false, tMs: 4321, sinceChangeMs: Math.floor(BLOOM_MS / 3),
  }
  assert.equal(Buffer.from(blake2b(utf8(JSON.stringify(renderField(input))), 32)).toString('hex'),
    '87dfccf60608eed42ea5b44e07aa21bdaf19b3ccf887990b02772c20023404c9')
})

test('renderSwatch golden digests: working clouds and resting mottle', () => {
  const base = { seed: ROOTS[0], hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0], intensity: 1 }
  const clouds = Buffer.from(blake2b(utf8(JSON.stringify(renderSwatch({ ...base, pattern: patternOf(DEFAULT_SETTINGS, 'working') }).dots)), 32)).toString('hex')
  assert.equal(clouds, '6c68603401f3ad39ff3f2806db04133c786077d22b18535db49cb3dca99d3f1c')
  const mottle = Buffer.from(blake2b(utf8(JSON.stringify(renderSwatch({ ...base, pattern: patternOf(DEFAULT_SETTINGS, 'resting') }).dots)), 32)).toString('hex')
  assert.equal(mottle, '7b2c9d34c11090a69e3c6223f2e4fd1f0c20327dc76f68ba9c6b288c494a5927')
})

// Every earlier digest used dials at 1, where `*` and `/` agree. These two render with
// density 0.5, contrast 2 and scale 1.3, so the shaper and the cloud's sigma are pinned too.
test('renderField golden digests: clouds and eyespot with the dials off unity', () => {
  const tuned = resolveSettings({
    patterns: {
      dial_clouds: { base: 'clouds', density: 0.5, contrast: 2, scale: 1.3 },
      dial_eye: { base: 'eyespot', density: 0.5, contrast: 2 },
    },
    states: {
      dc: { when: 'busy', pattern: 'dial_clouds', priority: 10, label: '' },
      de: { when: 'idle', pattern: 'dial_eye', priority: 10, label: '' },
    },
  })
  assert.deepEqual(tuned.warnings, [])
  const input = (pattern: ReturnType<typeof patternOf>) => ({
    seed: ROOTS[0], width: W, height: H, hueDeg: allocate(ROOTS[0], []).hue_deg, ground: GROUNDS[0],
    pattern, intensity: 1, motion: 'still' as const, reducedMotion: false, tMs: 0, sinceChangeMs: SETTLED_MS,
  })
  assert.equal(Buffer.from(blake2b(utf8(JSON.stringify(renderField(input(patternOf(tuned.settings, 'dc'))))), 32)).toString('hex'),
    'd0b2d97fdf8ae779009a1a28b7127a66c545d24f171a17c0342fe734e5d5d066')
  assert.equal(Buffer.from(blake2b(utf8(JSON.stringify(renderField(input(patternOf(tuned.settings, 'de'))))), 32)).toString('hex'),
    '7ba96cd9423dac06eca5b5796384e5b9cf4c6f2bdc6602e5836229c08705b5a2')
})
