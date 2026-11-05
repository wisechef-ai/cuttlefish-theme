// ACCEPTANCE CONTRACT — O2 state: the right state reaches the right session (locked).
// Fixtures in ./traces are REAL recordings of the upstream Desktop event stream (see ./traces/README.md); the
// synthetic cases below follow the Python half's own wire protocol (contract/README.md "Feed inputs").
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

interface Line { t: number; src: string; kind: string; session: string | null; payload: Record<string, unknown> }
const trace = (name: string): Line[] =>
  readFileSync(new URL(`./traces/${name}.jsonl`, import.meta.url), 'utf8').trim().split('\n').map((l: string) => JSON.parse(l))
    .filter((l: Line) => l.src === 'desktop.event' || l.src === 'desktop.state') as Line[]

/** Replay a trace up to (and including) `untilS` seconds; returns the model. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function replay(name: string, untilS: number, model?: any) {
  let m = model ?? D().initialFeed()
  for (const l of trace(name)) {
    if (l.t > untilS) break
    m = D().reduceFeed(m, { kind: l.kind, t: Math.round(l.t * 1000), session: l.session, payload: l.payload })
  }
  return m
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const stateAt = (m: any, stored: string) => D().stateFor(D().DEFAULT_SETTINGS, D().signalsOf(m, stored))

const MAIN = '20261015_232803_896d68'
const ERR = '20261015_234908_b706a2'
const KILL = '20261015_234530_e292be'

test('O2s.1 real trace (plain turn, clarify, approval): working while a turn runs, resting after, tool seen', () => {
  assert.equal(stateAt(replay('desktop-main', 26.0), MAIN), 'resting')
  assert.equal(stateAt(replay('desktop-main', 30.0), MAIN), 'working')
  assert.ok(D().signalsOf(replay('desktop-main', 50.0), MAIN).has('tool'), 'clarify tool.start → tool')
  assert.ok(!D().signalsOf(replay('desktop-main', 53.0), MAIN).has('tool'), 'tool.complete clears tool')
  assert.equal(stateAt(replay('desktop-main', 44.5), MAIN), 'resting', 'the focused session finished: seen, so resting')
  assert.equal(stateAt(replay('desktop-main', 999), MAIN), 'resting')
  assert.deepEqual(D().knownSessions(replay('desktop-main', 999)), [MAIN])
})

test('O2s.2 real trace (dead model): error is sticky after the turn ends, cleared by the next turn', () => {
  assert.equal(stateAt(replay('desktop-error', 100), ERR), 'working')
  const done = replay('desktop-error', 999)
  assert.equal(stateAt(done, ERR), 'error')
  const again = [
    { kind: 'state', t: 400_000, session: 'b7815629', payload: { gateway: 'open', busy: true, stored_session_id: ERR } },
    { kind: 'message.start', t: 400_001, session: 'b7815629', payload: {} },
  ].reduce((m, i) => D().reduceFeed(m, i), done)
  assert.equal(stateAt(again, ERR), 'working', 'the next turn clears the error')
})

test('O2s.3 real trace (backend killed): offline is not "working"; two runtimes map to one session', () => {
  const down = replay('desktop-kill', 30)
  assert.ok(D().signalsOf(down, KILL).has('offline'), 'gateway closed → offline')
  assert.ok(!D().signalsOf(down, KILL).has('busy'), 'a stale busy flag never shows while the gateway is down')
  assert.equal(stateAt(replay('desktop-kill', 38.0), KILL), 'resting')
  assert.equal(stateAt(replay('desktop-kill', 45.0), KILL), 'working', 'the new runtime 26f4e957 is the same session')
  assert.deepEqual(D().knownSessions(replay('desktop-kill', 999)), [KILL])
})

const ev = (kind: string, t: number, session: string | null, payload: Record<string, unknown> = {}) => ({ kind, t, session, payload })
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function run(...inputs: ReturnType<typeof ev>[]): any {
  return inputs.reduce((m, i) => D().reduceFeed(m, i), D().initialFeed())
}
const OPEN = (t: number, focusRt: string, focusStored: string) =>
  ev('state', t, null, { gateway: 'open', focused_session_id: focusRt, focused_stored_session_id: focusStored })
const MAP = (t: number, rt: string, stored: string) => ev('session.info', t, rt, { stored_session_id: stored })
const BUSY = (t: number, rt: string, stored: string, busy = true) =>
  ev('state', t, rt, { gateway: 'open', busy, stored_session_id: stored })

test('O2s.4 finished unseen: a turn that completes off-screen is marked until the user looks at it', () => {
  const base = [OPEN(0, 'a', 'SA'), MAP(1, 'a', 'SA'), MAP(2, 'b', 'SB'),
    ev('message.start', 3, 'b'), ev('message.complete', 9, 'b', { status: 'complete' })]
  const m = run(...base)
  assert.equal(stateAt(m, 'SB'), 'finished_unseen')
  assert.equal(stateAt(m, 'SA'), 'resting')
  assert.equal(stateAt(D().reduceFeed(m, OPEN(10, 'b', 'SB')), 'SB'), 'resting', 'focusing it clears unseen')
  const interrupted = run(OPEN(0, 'a', 'SA'), MAP(2, 'b', 'SB'), ev('message.start', 3, 'b'),
    ev('message.complete', 9, 'b', { status: 'interrupted' }))
  assert.equal(stateAt(interrupted, 'SB'), 'resting', 'an interrupted turn is not news')
  const early = run(ev('message.start', 3, 'b'), ev('message.complete', 9, 'b', { status: 'complete' }),
    OPEN(10, 'a', 'SA'), MAP(11, 'b', 'SB'))
  assert.equal(stateAt(early, 'SB'), 'finished_unseen', 'events before the runtime→stored mapping are buffered, not lost')
})

test('O2s.5 needs you via the Python half: per request, survives a second request, cleared on resolve or turn end', () => {
  const P = 'plugin.cuttlefish-theme.needs_you'
  const m1 = run(OPEN(0, 'a', 'SA'), MAP(1, 'b', 'SB'), BUSY(2, 'b', 'SB'), ev('message.start', 2, 'b'),
    ev(P, 3, null, { session_id: 'SB', session_key: 'SB', request_id: 'r1', kind: 'approval', active: true }),
    ev(P, 4, null, { session_id: 'SB', session_key: 'SB', request_id: 'r2', kind: 'clarify', active: true }))
  assert.equal(stateAt(m1, 'SB'), 'needs_you')
  assert.equal(stateAt(m1, 'SA'), 'resting', 'needs-you never leaks into another session')
  const m2 = D().reduceFeed(m1, ev(P, 5, null, { session_id: 'SB', session_key: 'SB', request_id: 'r1', kind: 'approval', active: false }))
  assert.equal(stateAt(m2, 'SB'), 'needs_you', 'r2 is still open')
  const m3 = D().reduceFeed(m2, ev(P, 6, null, { session_id: 'SB', session_key: 'SB', request_id: 'r2', kind: 'clarify', active: false }))
  assert.equal(stateAt(m3, 'SB'), 'working')
  const lost = D().reduceFeed(m1, ev('message.complete', 9, 'b', { status: 'complete' }))
  assert.notEqual(stateAt(lost, 'SB'), 'needs_you', 'a lost resolve cannot strand needs-you after the turn ends')
  const ignored = run(OPEN(0, 'a', 'SA'), ev(P, 3, null, { request_id: 'r9', active: true }))
  assert.deepEqual(D().knownSessions(ignored).filter((s: string) => s !== 'SA'), [], 'an event with no session is ignored')
})

test('O2s.6 error via the Python half (non-retryable API error) shows before the turn even ends', () => {
  const m = run(OPEN(0, 'a', 'SA'), MAP(1, 'a', 'SA'), BUSY(2, 'a', 'SA'), ev('message.start', 2, 'a'),
    ev('plugin.cuttlefish-theme.error', 3, null, { session_id: 'SA', session_key: 'SA', retryable: false }))
  assert.equal(stateAt(m, 'SA'), 'error')
  assert.equal(stateAt(D().reduceFeed(m, ev('message.start', 9, 'a')), 'SA'), 'working', 'a new turn clears it; the session is still busy')
})

test('O2s.7 the other signals: compacting, subagents, whole busy map snapshots', () => {
  let m = run(OPEN(0, 'a', 'SA'), MAP(1, 'a', 'SA'), ev('message.start', 2, 'a'),
    ev('status.update', 3, 'a', { kind: 'compacting' }), ev('subagent.start', 4, 'a'), ev('subagent.start', 5, 'a'))
  assert.ok(D().signalsOf(m, 'SA').has('compacting'))
  assert.ok(D().signalsOf(m, 'SA').has('subagents'))
  m = D().reduceFeed(m, ev('subagent.complete', 6, 'a'))
  assert.ok(D().signalsOf(m, 'SA').has('subagents'), 'one of two subagents is still running')
  m = D().reduceFeed(m, ev('subagent.complete', 7, 'a'))
  assert.ok(!D().signalsOf(m, 'SA').has('subagents'))
  m = D().reduceFeed(m, ev('message.complete', 8, 'a', { status: 'complete' }))
  assert.ok(!D().signalsOf(m, 'SA').has('compacting'), 'turn end clears compacting')
  const snap = run(OPEN(0, 'a', 'SA'), MAP(1, 'a', 'SA'), MAP(1, 'c', 'SC'),
    ev('state', 2, null, { gateway: 'open', busyBySession: { a: true, c: true } }),
    ev('state', 3, null, { gateway: 'open', busyBySession: { a: true } }))
  assert.ok(D().signalsOf(snap, 'SA').has('busy'))
  assert.ok(!D().signalsOf(snap, 'SC').has('busy'), 'a map snapshot replaces: absent runtimes are no longer busy')
})

test('O2s.8 reduceFeed is pure: the previous model is never mutated; garbage input is ignored, never thrown', () => {
  const m0 = run(OPEN(0, 'a', 'SA'), MAP(1, 'a', 'SA'))
  const frozen = JSON.stringify(m0)
  D().reduceFeed(m0, ev('message.start', 2, 'a'))
  assert.equal(JSON.stringify(m0), frozen)
  for (const junk of [ev('message.start', 3, null), ev('nonsense', 3, 'a'), { kind: 'state', t: 4 },
    ev('plugin.cuttlefish-theme.needs_you', 5, null, { session_id: 42 }), ev('active_list', 6, null, { sessions: 'x' })]) {
    assert.doesNotThrow(() => D().reduceFeed(m0, junk))
  }
})
