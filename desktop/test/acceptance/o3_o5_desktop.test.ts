// ACCEPTANCE CONTRACT — O3 (desktop half) + O5 (desktop half), pure decisions (locked).
// SPEC C9: with the Python half off, "needs you" falls back to polling session.active_list.
// SDK rule: never poll host.request faster than a few seconds. Ceiling ↔ floor: polling is slow and stops when the
// Python half is on AND it actually finds the waiting session when it runs.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}
const ev = (kind: string, t: number, session: string | null, payload: Record<string, unknown> = {}) => ({ kind, t, session, payload })
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const run = (...inputs: ReturnType<typeof ev>[]): any => inputs.reduce((m, i) => D().reduceFeed(m, i), D().initialFeed())
const OPEN = ev('state', 0, null, { gateway: 'open', focused_session_id: 'a', focused_stored_session_id: 'SA' })

test('O3.1 Python half off or unknown → poll session.active_list, every 3–10 s; on → no polling', () => {
  for (const m of [run(OPEN), run(OPEN, ev('python.health', 1, null, { ok: false }))]) {
    const p = D().pollPlan(m, 5000)
    assert.equal(p.pollActiveList, true)
    assert.ok(p.intervalMs >= 3000 && p.intervalMs <= 10_000, `interval ${p.intervalMs}`)
  }
  assert.equal(D().pollPlan(run(OPEN, ev('python.health', 1, null, { ok: true })), 5000).pollActiveList, false)
  const down = run(ev('state', 0, null, { gateway: 'closed' }), ev('python.health', 1, null, { ok: false }))
  assert.equal(D().pollPlan(down, 5000).pollActiveList, false, 'never poll a gateway that is not open')
})

test('O3.2 a Python event proves the half is on, even if /health failed', () => {
  const m = run(OPEN, ev('python.health', 1, null, { ok: false }),
    ev('plugin.cuttlefish-theme.needs_you', 2, null, { session_id: 'SB', session_key: 'SB', request_id: 'r', kind: 'approval', active: true }))
  assert.equal(D().pollPlan(m, 5000).pollActiveList, false)
})

test('O3.3 the poll result drives needs-you on its own (status "waiting"), and learns runtime → stored', () => {
  const S = D().stateFor
  const waiting = run(OPEN, ev('python.health', 1, null, { ok: false }),
    ev('active_list', 2, null, { sessions: [{ id: 'b', session_key: 'SB', status: 'waiting' }, { id: 'a', session_key: 'SA', status: 'idle' }] }))
  assert.equal(S(D().DEFAULT_SETTINGS, D().signalsOf(waiting, 'SB')), 'needs_you')
  assert.equal(S(D().DEFAULT_SETTINGS, D().signalsOf(waiting, 'SA')), 'resting')
  assert.deepEqual(D().knownSessions(waiting), ['SA', 'SB'])
  const later = D().reduceFeed(waiting, ev('active_list', 6, null, { sessions: [{ id: 'b', session_key: 'SB', status: 'working' }] }))
  assert.notEqual(S(D().DEFAULT_SETTINGS, D().signalsOf(later, 'SB')), 'needs_you', 'the next poll clears it')
  const busyNow = D().reduceFeed(later, ev('state', 7, 'b', { gateway: 'open', busy: true }))
  assert.ok(D().signalsOf(busyNow, 'SB').has('busy'), 'the mapping learned from the poll is used by later runtime events')
})

test('O5.1 configPlan: refetch the settings exactly when the config mtime changes (first sight included)', () => {
  let w = D().initialConfigWatch()
  let r = D().configPlan(w, 1000)
  assert.equal(r.refetch, true, 'first sight fetches')
  w = r.next
  r = D().configPlan(w, 1000)
  assert.equal(r.refetch, false, 'same mtime: nothing to do')
  w = r.next
  r = D().configPlan(w, '1000:2')
  assert.equal(r.refetch, true, 'an opaque version token that changes counts')
  w = r.next
  r = D().configPlan(w, null)
  assert.equal(r.refetch, false, 'an unreadable mtime keeps the last settings, never resets them')
  w = r.next
  r = D().configPlan(w, '1000:2')
  assert.equal(r.refetch, false, 'and recovering to the same token does not refetch')
})
