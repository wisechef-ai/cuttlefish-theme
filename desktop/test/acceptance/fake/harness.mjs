// ACCEPTANCE CONTRACT — load desktop/plugin.js under the fake host with a manual clock (locked).
import { register } from 'node:module'

import { install } from './dom.mjs'
import { fake } from './sdk.mjs'

register(new URL('./loader.mjs', import.meta.url).href)
install()

let loads = 0

export function makeCtx() {
  const state = { now: 0, contributions: [], disposers: [], timers: [], listeners: [], rest: [], storage: new Map(), disposed: false }
  let restResponder = async path => { throw new Error(`fake ctx.rest: no responder for ${path}`) }
  const track = fn => { state.disposers.push(fn); return fn }
  const ctx = {
    source: 'plugin:cuttlefish-theme',
    register(c) {
      const rec = { ...c, live: true }
      state.contributions.push(rec)
      return track(() => { rec.live = false })
    },
    registerMany(cs) { const ds = cs.map(c => ctx.register(c)); return () => ds.forEach(d => d()) },
    registerSettingsPage: () => () => {},
    rest: (path, opts) => { state.rest.push({ path, opts, at: state.now }); return restResponder(path, opts) },
    socket: () => () => {},
    onEvent(type, fn) {
      const { host } = globalThis.__fakeSdk
      return track(host.onEvent(type, fn))
    },
    onDispose: fn => { track(fn) },
    setTimeout(fn, ms) {
      const t = { fn, ms, kind: 'timeout', due: state.now + ms, live: true }
      state.timers.push(t)
      return track(() => { t.live = false })
    },
    setInterval(fn, ms) {
      const t = { fn, ms, kind: 'interval', due: state.now + ms, live: true }
      state.timers.push(t)
      return track(() => { t.live = false })
    },
    addEventListener(target, type, fn) {
      const l = { target, type, fn, live: true }
      state.listeners.push(l)
      target.addEventListener?.(type, fn)
      return track(() => { l.live = false; target.removeEventListener?.(type, fn) })
    },
    os: { notify: () => {}, openExternal: () => {}, reveal: () => {}, clipboard: { writeText: () => {} } },
    pet: { say: () => {}, visible: false },
    preview: { executeJavaScript: () => { throw new Error('fake: preview not allowed') } },
    storage: {
      get: (k, d) => (state.storage.has(k) ? state.storage.get(k) : d),
      set: (k, v) => { state.storage.set(k, v) }, remove: k => { state.storage.delete(k) },
    },
  }
  const api = {
    ctx, state,
    respondRest(fn) { restResponder = async (p, o) => fn(p, o) },
    /** Advance the manual clock, firing due timers in order; returns after pending promises settle. */
    async advance(ms) {
      const end = state.now + ms
      for (;;) {
        const due = state.timers.filter(t => t.live && t.due <= end).sort((a, b) => a.due - b.due)[0]
        if (!due) break
        state.now = due.due
        if (due.kind === 'interval') due.due += Math.max(1, due.ms)
        else due.live = false
        await due.fn()
        await flush()
      }
      state.now = end
      await flush()
    },
    dispose() { state.disposed = true; for (const d of [...state.disposers].reverse()) d() },
    live: area => state.contributions.filter(c => c.live && (typeof area === 'string' ? c.area === area : area(c.area))),
  }
  return api
}

export const flush = async () => { for (let i = 0; i < 10; i++) await new Promise(r => setImmediate(r)) }

/** Fresh module instance of desktop/plugin.js, registered against a fresh fake ctx. */
export async function loadPlugin() {
  const sdk = await import('./sdk.mjs')
  globalThis.__fakeSdk = sdk
  sdk.fake.reset()
  const url = new URL('../../../plugin.js', import.meta.url)
  url.search = `?load=${++loads}`
  const mod = await import(url.href)
  const h = makeCtx()
  mod.default.register(h.ctx)
  await flush()
  return { mod, h, sdk, fake }
}
