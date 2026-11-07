// Unit: the feed reducer's pinned semantics, beyond what the locked O2s/O3 traces exercise —
// buffer order, map replacement, poll gating, purity and garbage tolerance.
// Structure ported from origin/agent/tori/cf2909-d2-core-state (per-runtime busy, buffered message.*).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { initialFeed, knownSessions, pollPlan, reduceFeed, signalsOf, type FeedInput, type FeedModel } from '../../src/domain/feed.ts'

const ev = (kind: string, session: string | null, payload: Record<string, unknown> | null, t = 0): FeedInput =>
  ({ kind, t, session, payload })

function run(events: FeedInput[], from: FeedModel = initialFeed()): FeedModel {
  let m = from
  for (const e of events) m = reduceFeed(m, e)
  return m
}

const gw = (open: boolean, session = 'rt-1', over: Record<string, unknown> = {}): FeedInput =>
  ev('state', session, { gateway: open ? 'open' : 'closed', ...over })

const sig = (m: FeedModel, s: string): string[] => [...signalsOf(m, s)].sort()

test('message.start alone never makes a session busy; only host busy state does', () => {
  const m = run([ev('session.info', 'rt-1', { stored_session_id: 's1' }), ev('message.start', 'rt-1', {})])
  assert.ok(!sig(m, 's1').includes('busy'))
  const busy = run([ev('session.info', 'rt-1', { stored_session_id: 's1' }), ev('state', 'rt-1', { gateway: 'open', busy: true })])
  assert.ok(sig(busy, 's1').includes('busy'))
})

test('gateway not open: offline, never busy — even mid-turn', () => {
  const m = run([
    ev('session.info', 'rt-1', { stored_session_id: 's1' }),
    ev('state', 'rt-1', { gateway: 'open', busy: true }),
    ev('state', 'rt-1', { gateway: 'closed', busy: true }),
    ev('message.start', 'rt-1', {}),
  ])
  assert.deepEqual(sig(m, 's1'), ['idle', 'offline'])
})

test('busyBySession is a snapshot: it REPLACES the set, absent runtimes stop being busy', () => {
  const m = run([
    gw(true, 'rt-1'),
    ev('session.info', 'rt-2', { stored_session_id: 's2' }),
    ev('state', 'rt-1', { gateway: 'open', busy: true }),
    ev('state', 'rt-2', { gateway: 'open', busy: true }),
    ev('state', null, { gateway: 'open', busyBySession: { 'rt-2': true } }),
  ])
  assert.ok(!sig(m, 's1').includes('busy'), 'rt-1 absent from the map: no longer busy')
  assert.ok(sig(m, 's2').includes('busy'), 'rt-2 mapped to s2 and busy')
})

test('buffered message.* apply in order when the mapping arrives, against the focus at apply time', () => {
  // rt-9 completes while unmapped and while s2 is focused; the mapping arrives afterwards
  const m = run([
    ev('session.info', 'rt-2', { stored_session_id: 's2' }),
    ev('state', 'rt-2', { gateway: 'open', focused_session_id: 'rt-2', focused_stored_session_id: 's2' }),
    ev('message.complete', 'rt-9', { status: 'complete' }, 100),
    ev('session.info', 'rt-9', { stored_session_id: 's9' }, 200),
  ])
  assert.ok(sig(m, 's9').includes('unseen'), 'the buffered complete lands once the mapping is known')
  // now the user focuses s9: unseen clears
  const seen = run([ev('state', 'rt-9', { gateway: 'open', focused_session_id: 'rt-9', focused_stored_session_id: 's9' })], m)
  assert.ok(!sig(seen, 's9').includes('unseen'))
})

test('failed is sticky past the turn end and cleared by the next message.start of that session', () => {
  const base: FeedInput[] = [gw(true, 'rt-1'), ev('session.info', 'rt-1', { stored_session_id: 's1' })]
  const failed = run([...base, ev('message.complete', 'rt-1', { status: 'error' })])
  assert.ok(sig(failed, 's1').includes('failed'))
  const still = run([...base, ev('message.complete', 'rt-1', { status: 'error' }), ev('message.start', 'rt-2', {})], failed)
  assert.ok(sig(still, 's1').includes('failed'), 'another session\'s start does not clear it')
  const cleared = run([ev('message.start', 'rt-1', {})], still)
  assert.ok(!sig(cleared, 's1').includes('failed'))
})

test('plugin needs_you: per request, second request survives, resolve or turn end clears', () => {
  const add = (id: string): FeedInput => ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: id, active: true })
  const m = run([gw(true), add('q1'), add('q2')])
  assert.ok(sig(m, 's1').includes('needs_input'))
  const one = run([ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: 'q1', active: false })], m)
  assert.ok(sig(one, 's1').includes('needs_input'), 'q2 is still open')
  const done = run([ev('message.complete', 'rt-1', { status: 'complete' }), ev('session.info', 'rt-1', { stored_session_id: 's1' })], one)
  // (the mapping arrives after the complete: it is buffered and applied, clearing the queue)
  assert.ok(!sig(done, 's1').includes('needs_input'))
})

test('plugin error: non-retryable fails the session, retryable does not; either proves the half is on', () => {
  const err = run([gw(true), ev('plugin.cuttlefish-theme.error', null, { session_id: 's1' })])
  assert.ok(sig(err, 's1').includes('failed'))
  assert.equal(pollPlan(err, 0).pollActiveList, false, 'a plugin event means no polling')
  const retry = run([gw(true), ev('plugin.cuttlefish-theme.error', null, { session_id: 's1', retryable: true })])
  assert.ok(!sig(retry, 's1').includes('failed'))
  assert.equal(pollPlan(retry, 0).pollActiveList, false)
})

test('pollPlan: only while the gateway is open and the Python half is off or unknown (locked O3.1 rule)', () => {
  assert.equal(pollPlan(initialFeed(), 0).pollActiveList, false, 'gateway unknown: nothing to poll')
  const open = run([gw(true)])
  assert.deepEqual(pollPlan(open, 0), { pollActiveList: true, intervalMs: 5000 })
  const healthy = run([ev('python.health', null, { ok: true })], open)
  assert.equal(pollPlan(healthy, 0).pollActiveList, false, 'health ok: the half is on')
  const sick = run([ev('python.health', null, { ok: false })], healthy)
  assert.equal(pollPlan(sick, 0).pollActiveList, true, 'a FAILED health answer is off/unknown: poll again')
  const plugin = run([ev('plugin.cuttlefish-theme.needs_you', null, { session_id: 's1', request_id: 'r', active: true })], sick)
  assert.equal(pollPlan(plugin, 0).pollActiveList, false, 'a plugin event proves the half is on, even after /health failed')
})

test('active_list: waiting drives needs_input on its own; never busy; gone sessions lose it', () => {
  const m = run([gw(true), ev('active_list', null, { sessions: [{ id: 'rt-1', session_key: 's1', status: 'waiting' }] })])
  assert.deepEqual(sig(m, 's1'), ['idle', 'needs_input'])
  const gone = run([ev('active_list', null, { sessions: [{ id: 'rt-1', session_key: 's1', status: 'idle' }] })], m)
  assert.ok(!sig(gone, 's1').includes('needs_input'))
})

test('tool calls and compacting surface as signals; a turn boundary closes both; garbage never throws', () => {
  const base: FeedInput[] = [gw(true, 'rt-1'), ev('session.info', 'rt-1', { stored_session_id: 's1' })]
  const working = run([...base,
    ev('tool.start', 'rt-1', { tool_call_id: 't2' }),
    ev('tool.start', 'rt-1', { tool_call_id: 't1' }),
    ev('tool.start', 'rt-1', { tool_call_id: 't1' }),
    ev('status.update', 'rt-1', { kind: 'compacting' }),
  ])
  assert.deepEqual(sig(working, 's1'), ['compacting', 'idle', 'tool'])
  const nextTurn = run([ev('message.start', 'rt-1', {})], working)
  assert.deepEqual(sig(nextTurn, 's1'), ['idle'], 'a new turn closes tools and compacting')
})

test('subagents: counted per runtime, cleared at a turn boundary', () => {
  const m = run([gw(true, 'rt-1'), ev('session.info', 'rt-1', { stored_session_id: 's1' }),
    ev('subagent.start', 'rt-1', {}), ev('subagent.start', 'rt-1', {}), ev('subagent.complete', 'rt-1', {})])
  assert.ok(sig(m, 's1').includes('subagents'))
  const cleared = run([ev('message.start', 'rt-1', {})], m)
  assert.ok(!sig(cleared, 's1').includes('subagents'))
})

test('reduceFeed is pure and garbage-tolerant: the model is never mutated, nothing throws', () => {
  const m0 = run([gw(true), ev('session.info', 'rt-1', { stored_session_id: 's1' }), ev('message.start', 'rt-1', {})])
  const snap = JSON.stringify(m0)
  const junk: unknown[] = [null, 3, 'x', [], {}, { kind: 7 }, { kind: 'state', payload: 'not-a-map' },
    { kind: 'message.start', session: 9 }, { kind: 'active_list', payload: { sessions: 'no' } },
    { kind: 'active_list', payload: { sessions: [{ id: '__proto__', session_key: 'x', status: 'waiting' }] } }]
  for (const j of junk) {
    assert.doesNotThrow(() => reduceFeed(m0, j as FeedInput))
  }
  assert.equal(JSON.stringify(m0), snap)
  assert.deepEqual(knownSessions(m0), ['s1'])
})

test('an unknown session carries no signals at all', () => {
  assert.deepEqual([...signalsOf(initialFeed(), 'nobody')], [])
})

// fix-m4 D1 — real orderings from the M4 capture (hercules x9.log): on a direct focus switch the runtime-id
// atom lags the stored-id atom, so the snapshot carries (OLD runtime id, NEW stored id).
const snap = (rtFocus: string | null, stored: string | null, extra: Record<string, unknown> = {}): FeedInput =>
  ev('state', rtFocus, { gateway: 'open', ...(rtFocus ? { focused_session_id: rtFocus } : {}), ...(stored ? { focused_stored_session_id: stored } : {}), ...extra })

const twoSessions = (): FeedModel => run([
  snap('rtA', 'A', { busyBySession: {} }),
  ev('session.info', 'rtA', { stored_session_id: 'A' }),
  snap('rtB', 'B', { busyBySession: {} }),
  ev('session.info', 'rtB', { stored_session_id: 'B' }),
  // focus B -> A with B mid-turn; the rt atom lags: (rtB, A)
  snap('rtB', 'B', { busyBySession: { rtB: true } }),
])

test('D1: a lagging runtime atom (old rt, new stored) never maps the session being LEFT to the one ENTERED', () => {
  const m = run([snap('rtB', 'A', { busyBySession: { rtB: true } })], twoSessions())
  assert.equal(m.storedOf.rtB, 'B')
  assert.ok(sig(m, 'B').includes('busy'), 'B (left, still running) is working')
  assert.ok(!sig(m, 'A').includes('busy'), 'A (entered) is not working')
})

test('D1: finished_unseen fires when a turn ends in the session that was left by a direct switch', () => {
  let m = run([snap('rtB', 'A', { busyBySession: { rtB: true } })], twoSessions())
  m = run([snap('rtA', 'A', { busyBySession: { rtB: true } })], m) // the atoms settle
  m = run([ev('message.complete', 'rtB', { status: 'complete' }), snap('rtA', 'A', { busyBySession: {} })], m)
  assert.ok(sig(m, 'B').includes('unseen'), 'B finished unseen')
  assert.ok(!sig(m, 'A').includes('unseen'))
  assert.ok(!sig(m, 'B').includes('busy'))
})

test('D1: the mirror lag (new rt, old stored) is not learned either', () => {
  const m = run([snap('rtA', 'B')], run([snap('rtA', 'A'), ev('session.info', 'rtA', { stored_session_id: 'A' }), snap('rtB', 'B'), ev('session.info', 'rtB', { stored_session_id: 'B' })]))
  assert.equal(m.storedOf.rtA, 'A')
  assert.equal(m.storedOf.rtB, 'B')
  const lag = run([snap('rtB', 'A')], run([snap('rtA', 'A'), ev('session.info', 'rtA', { stored_session_id: 'A' }), ev('session.info', 'rtB', { stored_session_id: 'B' })]))
  assert.equal(lag.storedOf.rtB, 'B')
})

test('D1: Ctrl+N (new empty chat, no stored id) unfocuses the stored session, so a turn finishing then is unseen', () => {
  let m = run([
    snap('rtA', 'A'), ev('session.info', 'rtA', { stored_session_id: 'A' }),
    snap('rtA', 'A', { busyBySession: { rtA: true } }),
  ])
  m = run([ev('state', 'rtN', { gateway: 'open', focused_session_id: 'rtN', focused_stored_session_id: null, busyBySession: { rtA: true } })], m)
  assert.equal(m.focusedStored, null)
  m = run([ev('message.complete', 'rtA', { status: 'complete' }), snap('rtN', null, { busyBySession: {} })], m)
  assert.ok(sig(m, 'A').includes('unseen'))
})

test('D1: a first-ever focused pair is still learned', () => {
  const m = run([snap('rtA', 'A')])
  assert.equal(m.storedOf.rtA, 'A')
  assert.equal(m.focusedStored, 'A')
})

test('D1: a mapped runtime is never re-pointed by a focused pair naming a stored id nobody has yet', () => {
  const m = run([snap('rtB', 'C')], twoSessions())
  assert.equal(m.storedOf.rtB, 'B')
})

test('D1: an unmapped new runtime beside the OLD stored id (rt atom ahead) is not learned', () => {
  const m = run([snap('rtN', 'A')], twoSessions())
  assert.equal(m.storedOf.rtN, undefined)
  assert.equal(m.storedOf.rtA, 'A')
})
