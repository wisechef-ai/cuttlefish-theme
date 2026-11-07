// Unit contract of the config watch + poll (adapters lane, C5/C9): the mtime watch fetches
// /config exactly on change (first sight included, ≥ 2 s cadence, one early kick), the poll
// runs only while the Python half is off/unknown at the domain's pollPlan cadence, and
// dispose leaves no timer live.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { FIRST_WATCH_MS, WATCH_MS, wireWatch, type WatchDoors } from '../../../src/adapters/configwatch.ts'
import { initialFeed, POLL_INTERVAL_MS, pollPlan, reduceFeed, type FeedInput } from '../../../src/domain/index.ts'

interface Timer { fn: () => void; ms: number; kind: 'timeout' | 'interval'; due: number; live: boolean }

function fakeDoors(answer: { mtime?: number | string; config?: unknown; health?: boolean; list?: unknown }) {
  const state = { now: 0, timers: [] as Timer[], requests: [] as { method: string; at: number }[], rest: [] as { path: string; at: number }[] }
  const doors: WatchDoors = {
    async request(method) {
      state.requests.push({ method, at: state.now })
      if (method === 'config.get') return { mtime: answer.mtime ?? 1 }
      if (method === 'session.active_list') return { sessions: answer.list ?? [] }
      throw new Error(`unexpected ${method}`)
    },
    async rest(path) {
      state.rest.push({ path, at: state.now })
      if (path === '/config') return { settings: answer.config ?? {}, warnings: [], rev: 'r' }
      if (path === '/health') {
        if (answer.health === false) throw new Error('404')
        return { ok: true, version: '2.0.0' }
      }
      throw new Error(`unexpected ${path}`)
    },
    setTimeout(fn, ms) { const t = { fn, ms, kind: 'timeout' as const, due: state.now + ms, live: true }; state.timers.push(t); return () => { t.live = false } },
    setInterval(fn, ms) { const t = { fn, ms, kind: 'interval' as const, due: state.now + ms, live: true }; state.timers.push(t); return () => { t.live = false } },
  }
  const settle = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setImmediate(r)) }
  const advance = async (ms: number) => {
    const end = state.now + ms
    for (;;) {
      const due = state.timers.filter(t => t.live && t.due <= end).sort((a, b) => a.due - b.due)[0]
      if (!due) break
      state.now = due.due
      if (due.kind === 'interval') due.due += Math.max(1, due.ms)
      else due.live = false
      await due.fn()
      await settle()
    }
    state.now = end
    await settle()
  }
  return { doors, state, advance }
}

const hooks = (feeds: FeedInput[] = [], settings: unknown[] = [], poll = () => true) => ({
  onFeed: (i: FeedInput) => feeds.push(i),
  onSettings: (s: unknown) => settings.push(s),
  pollWanted: poll,
})

test('config: the first sight fetches early, then only on mtime change, ≥ 2 s apart', async () => {
  const f = fakeDoors({ mtime: 1 })
  const seen = hooks()
  const stop = wireWatch(f.doors, seen)
  await f.advance(FIRST_WATCH_MS)
  assert.equal(f.state.rest.filter(r => r.path === '/config').length, 1, 'the early kick fetches')
  await f.advance(3 * WATCH_MS)
  assert.equal(f.state.rest.filter(r => r.path === '/config').length, 1, 'an unchanged mtime refetches nothing')
  f.state.requests.length = 0
  await f.advance(WATCH_MS)
  assert.equal(f.state.requests.filter(r => r.method === 'config.get').length, 1, 'one mtime probe per watch tick')
  for (const t of f.state.timers.filter(x => x.kind === 'interval' && x.live)) {
    assert.ok(t.ms >= 2000, `a ${t.ms} ms interval is faster than the SDK allows`)
  }
  stop()
  assert.equal(f.state.timers.filter(t => t.live).length, 0, 'dispose stops every timer')
})

test('config: an mtime change refetches and applies; a failed fetch keeps the last settings', async () => {
  let mtime: number | string = 1
  const f = fakeDoors({ mtime: 1 })
  const applied: unknown[] = []
  const doors: WatchDoors = {
    ...f.doors,
    request: async (method, params) => {
      if (method === 'config.get') return { mtime }
      if (method === 'session.active_list') return { sessions: [] }
      throw new Error('no')
    },
  }
  const stop = wireWatch(doors, hooks([], applied))
  await f.advance(FIRST_WATCH_MS)
  assert.equal(applied.length, 1)
  mtime = 2
  await f.advance(WATCH_MS)
  assert.equal(applied.length, 2, 'the change refetches /config')
  assert.deepEqual(f.state.rest.map(r => r.path), ['/config', '/config'], 'the kick fetch, then the change')
  stop()
})

test('poll: python on → never polls; off → polls at the domain cadence and feeds active_list', async () => {
  const plan = (feeds: FeedInput[]) => pollPlan(feeds.reduce((m, i) => reduceFeed(m, i), initialFeed()), 0).pollActiveList
  const on = fakeDoors({ health: true })
  const onFeeds: FeedInput[] = [{ kind: 'state', t: 0, session: null, payload: { gateway: 'open' } }]
  const stopOn = wireWatch(on.doors, hooks(onFeeds, [], () => plan(onFeeds)))
  await on.advance(20_000)
  assert.equal(on.state.requests.filter(r => r.method === 'session.active_list').length, 0, 'python on: no polling')
  stopOn()

  const off = fakeDoors({ health: false, list: [{ id: 'b', session_key: 'SB', status: 'waiting' }] })
  const offFeeds: FeedInput[] = [{ kind: 'state', t: 0, session: null, payload: { gateway: 'open' } }]
  const stopOff = wireWatch(off.doors, hooks(offFeeds, [], () => plan(offFeeds)))
  await off.advance(20_000)
  const polls = off.state.requests.filter(r => r.method === 'session.active_list')
  assert.equal(polls.length, 4, 'a poll per POLL_INTERVAL_MS tick')
  assert.equal(POLL_INTERVAL_MS >= 3000 && POLL_INTERVAL_MS <= 10_000, true)
  assert.equal(offFeeds.filter(x => x.kind === 'python.health').length, 4, 'each poll tick probes /health first')
  const list = offFeeds.filter(x => x.kind === 'active_list')
  for (const x of list) {
    assert.deepEqual(x.payload, { sessions: [{ id: 'b', session_key: 'SB', status: 'waiting' }] }, 'the list is fed verbatim')
  }
  stopOff()
})

test('poll: a thrown poll is one missed poll, never a dead watch', async () => {
  const f = fakeDoors({ health: false })
  let throwOnce = true
  const doors: WatchDoors = { ...f.doors, request: async method => {
    if (method === 'session.active_list' && throwOnce) { throwOnce = false; throw new Error('boom') }
    return f.doors.request(method, {})
  } }
  const feeds: FeedInput[] = []
  const stop = wireWatch(doors, hooks(feeds, [], () => true))
  await f.advance(2 * POLL_INTERVAL_MS)
  assert.equal(f.state.rest.filter(r => r.path === '/config').length >= 1, true, 'the settings watch survived')
  stop()
})
