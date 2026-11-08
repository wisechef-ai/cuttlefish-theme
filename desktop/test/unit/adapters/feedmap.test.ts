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

test('feedmap: empty ids stay out, and an EMPTY busy map is forwarded while the flag is false (F2)', () => {
  const snap = stateSnapshot({
    activeSessionId: atom(null),
    busy: atom(false),
    busyBySession: atom({}),
    focusedSessionId: atom(''),
    focusedStoredSessionId: atom(null),
    gateway: atom('connecting'),
  }, 1)
  assert.equal(snap.session, null)
  assert.deepEqual(snap.payload, { gateway: 'connecting', busy: false, busyBySession: {} }, 'an empty map with a quiet flag is the authoritative "nobody busy"')
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

test('feedmap: parseGround understands what a real engine resolves a colour to (F1)', async () => {
  const { parseGround } = await import('../../../src/adapters/ground.ts')
  assert.equal(parseGround('color(srgb 0.980392 0.976471 0.968627)'), '#faf9f7', 'color-mix(in srgb) resolves to color(srgb …)')
  assert.equal(parseGround('color(srgb 0.078 0.078 0.086 / 1)'), '#141416')
  assert.equal(parseGround('rgb(250 249 247)'), '#faf9f7', 'space-separated rgb()')
  assert.equal(parseGround('rgb(250 249 247 / 0.5)'), null, 'a translucent ground is not a ground we can paint on')
  assert.equal(parseGround('rgba(0, 0, 0, 0)'), null, 'transparent (an unresolved var()) is no ground')
  assert.equal(parseGround('color-mix(in srgb, #fff 90%, transparent)'), null, 'an unresolved token stream is no ground')
})

test('feedmap: a present-but-emptied busyBySession map clears the busy set; the fake-only {} + busy:true keeps the flag (F2)', async () => {
  const { initialFeed, reduceFeed, signalsOf } = await import('../../../src/domain/index.ts')
  const mk = (map: Record<string, boolean>, busy: boolean): StateAtoms => ({
    activeSessionId: atom<string | null>('a'), busy: atom(busy), busyBySession: atom(map),
    focusedSessionId: atom<string | null>('a'), focusedStoredSessionId: atom<string | null>('SA'), gateway: atom('open'),
  })
  let feed = reduceFeed(initialFeed(), { kind: 'session.info', t: 0, session: 'a', payload: { stored_session_id: 'SA' } })
  feed = reduceFeed(feed, stateSnapshot(mk({ a: true, b: true }, true), 1))
  assert.ok(signalsOf(feed, 'SA').has('busy'))
  // the host drops the session's state entry: map {} and the focused chat is not busy
  const emptied = stateSnapshot(mk({}, false), 2)
  assert.deepEqual(emptied.payload?.busyBySession, {}, 'the authoritative empty map is forwarded')
  feed = reduceFeed(feed, emptied)
  assert.ok(!signalsOf(feed, 'SA').has('busy'), 'nobody is busy any more — no stale working')
  // the shape the contract fakes produce (flag only, map resting {}) still reads busy
  const flagOnly = stateSnapshot(mk({}, true), 3)
  assert.equal('busyBySession' in (flagOnly.payload ?? {}), false)
  assert.ok(signalsOf(reduceFeed(feed, flagOnly), 'SA').has('busy'))
})

test('feedmap: a percentage alpha is judged as a percentage', async () => {
  const { parseGround } = await import('../../../src/adapters/ground.ts')
  assert.equal(parseGround('rgb(1 2 3 / 50%)'), null)
  assert.equal(parseGround('rgb(1 2 3 / 100%)'), '#010203')
})

test('feedmap D1: a focused runtime with a null stored atom (Ctrl+N) forwards an explicit null; no focused runtime forwards nothing', () => {
  const base = { activeSessionId: atom<string | null>('rtN'), busy: atom(false), busyBySession: atom<Record<string, boolean>>({}), gateway: atom('open') }
  const fresh = stateSnapshot({ ...base, focusedSessionId: atom<string | null>('rtN'), focusedStoredSessionId: atom<string | null>(null) }, 1)
  assert.equal(fresh.payload?.focused_stored_session_id, null)
  assert.ok(Object.hasOwn(fresh.payload ?? {}, 'focused_stored_session_id'))
  const none = stateSnapshot({ ...base, focusedSessionId: atom<string | null>(null), focusedStoredSessionId: atom<string | null>(null) }, 2)
  assert.ok(!Object.hasOwn(none.payload ?? {}, 'focused_stored_session_id'))
})
