// Unit contract of the host→feed mapping (adapters lane): host.state atoms and host events
// become exactly the FeedInput kinds contract/README.md §Feed inputs pins, and garbage
// (missing ids, wrong payload shapes, unmodelled types) maps to null, never a throw.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { eventToFeed, FEED_EVENT_KINDS, stateSnapshot, type StateAtoms } from '../../../src/adapters/feedmap.ts'

const atom = <T>(v: T) => ({ get: (): T => v })

test('feedmap: a host event becomes its feed input, verbatim', () => {
  const e = { type: 'message.complete', session_id: 'rt1', payload: { status: 'complete' } }
  assert.deepEqual(eventToFeed(e, 7), { kind: 'message.complete', t: 7, session: 'rt1', payload: { status: 'complete' } })
  assert.equal(eventToFeed({ type: 'session.info', session_id: 'rt1', payload: { stored_session_id: 'SA' } }, 8)?.kind, 'session.info')
  const plugin = { type: 'plugin.cuttlefish-theme.needs_you', session_id: '', payload: { session_id: 'SA' } }
  assert.equal(eventToFeed(plugin, 9)?.kind, 'plugin.cuttlefish-theme.needs_you')
})

test('feedmap: unmodelled types and garbage map to null, never throw', () => {
  for (const bad of [
    { type: 'gateway.open' }, null, 7, { type: 4, session_id: 'a' },
    { type: 'message.start' }, { type: 'message.start', session_id: 3, payload: null },
  ] as Parameters<typeof eventToFeed>[0][]) {
    assert.equal(eventToFeed(bad, 0), null, JSON.stringify(bad))
  }
  assert.ok(FEED_EVENT_KINDS.has('plugin.cuttlefish-theme.error'))
})

test('feedmap: the state snapshot carries every documented field, absent doors omitted', () => {
  const atoms: StateAtoms = {
    activeSessionId: atom('a'),
    busy: atom(true),
    busyBySession: atom({ a: true }),
    focusedSessionId: atom('a'),
    focusedStoredSessionId: atom('SA'),
    gateway: atom('open'),
  }
  const snap = stateSnapshot(atoms, 3)
  assert.equal(snap.kind, 'state')
  assert.equal(snap.t, 3)
  assert.equal(snap.session, 'a')
  assert.deepEqual(snap.payload, {
    gateway: 'open', busy: true, busyBySession: { a: true }, focused_session_id: 'a', focused_stored_session_id: 'SA',
  })
})

test('feedmap: empty ids stay out of the snapshot (a null focus is not a mapping)', () => {
  const snap = stateSnapshot({
    activeSessionId: atom(null),
    busy: atom(false),
    busyBySession: atom({}),
    focusedSessionId: atom(''),
    focusedStoredSessionId: atom(null),
    gateway: atom('connecting'),
  }, 1)
  assert.equal(snap.session, null)
  assert.deepEqual(snap.payload, { gateway: 'connecting', busy: false, busyBySession: {} })
})

test('feedmap: a non-object busyBySession is omitted, a non-string gateway ignored downstream', () => {
  const snap = stateSnapshot({
    activeSessionId: atom(null),
    busy: atom(undefined as unknown as boolean),
    busyBySession: atom(undefined as unknown as Record<string, boolean>),
    focusedSessionId: atom(null),
    focusedStoredSessionId: atom(null),
    gateway: atom(''),
  }, 0)
  assert.deepEqual(snap.payload, {})
})

test('feedmap: parseGround reads the computed ground of the fake host exactly', async () => {
  const { parseGround } = await import('../../../src/adapters/ground.ts')
  assert.equal(parseGround('rgb(20, 20, 22)'), '#141416')
  assert.equal(parseGround('rgb( 251, 251, 250 )'), '#fbfbfa')
  assert.equal(parseGround('#2E3440'), '#2e3440')
  assert.equal(parseGround('oklch(0.2 0 0)'), null)
  assert.equal(parseGround(''), null)
})
