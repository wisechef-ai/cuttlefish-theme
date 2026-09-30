/**
 * cf-spike — scratch UNIFIED package desktop half for cuttlefish P0 spikes 07–10, 14.
 * NOT the product. It exists to answer platform questions with real renders:
 *   14  a status-bar chip + a sidebar nav row become visible once enabled
 *   10  a load stamp (performance.now / Date.now) for time-to-first-pixel
 *   07  host.onEvent('*') recorder + host.state snapshots
 *   08  ctx.rest('/ping') against dashboard/plugin_api.py
 *   09  host.sessions.setColor probe
 * Everything it learns is published on window.__cfSpike for the Playwright harness.
 */
import { host, SIDEBAR_NAV_AREA, ROUTES_AREA, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'cf-spike'
const MAX_EVENTS = 4000

function probe() {
  const w = window
  if (!w.__cfSpike) {
    w.__cfSpike = { loads: [], events: [], states: [], rest: [], errors: [] }
  }
  return w.__cfSpike
}

function snapshotState(reason) {
  const s = host.state
  const read = atom => {
    try {
      return atom ? atom.get() : undefined
    } catch (error) {
      return `ERR ${String(error)}`
    }
  }
  const snap = {
    t: Date.now(),
    reason,
    busyBySession: read(s.busyBySession),
    focusedSessionId: read(s.focusedSessionId),
    focusedStoredSessionId: read(s.focusedStoredSessionId),
    focusedSessionOwner: read(s.focusedSessionOwner),
    activeSessionId: read(s.activeSessionId),
    gateway: read(s.gateway),
    profile: read(s.profile),
  }
  const p = probe()
  p.states.push(snap)
  if (p.states.length > MAX_EVENTS) p.states.shift()
  return snap
}

function Chip() {
  const busy = useValue(host.state.busyBySession) ?? {}
  const n = Object.values(busy).filter(Boolean).length
  return jsxs('span', {
    'data-testid': 'cf-spike-chip',
    className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] text-(--ui-text-secondary)',
    children: [
      jsx('span', { style: { width: 8, height: 8, borderRadius: 999, background: 'var(--ui-accent)', display: 'inline-block' } }),
      `CF-SPIKE ${n} busy`,
    ],
  })
}

function Page() {
  return jsx('div', {
    'data-testid': 'cf-spike-page',
    className: 'p-6 text-sm text-(--ui-text-secondary)',
    children: 'cf-spike route — scratch plugin for cuttlefish P0',
  })
}

export default {
  id: ID,
  name: 'CF Spike',
  register(ctx) {
    const p = probe()
    p.ctx = ctx
    p.host = host
    p.loads.push({ t: Date.now(), perf: performance.now() })

    // 07: every gateway event, verbatim (bounded).
    ctx.onEvent('*', event => {
      const rec = { t: Date.now(), event }
      p.events.push(rec)
      if (p.events.length > MAX_EVENTS) p.events.shift()
    })

    // 07: state atoms, on change.
    for (const key of ['busyBySession', 'focusedSessionId', 'focusedStoredSessionId', 'gateway']) {
      const atom = host.state[key]
      if (atom && typeof atom.listen === 'function') {
        const off = atom.listen(() => snapshotState(key))
        ctx.onDispose?.(off)
      }
    }
    snapshotState('register')

    // 08: REST + socket probes, callable from the harness.
    p.restGet = async (path = '/ping') => {
      const t0 = performance.now()
      try {
        const body = await ctx.rest(path, { timeoutMs: 8000 })
        const r = { ok: true, path, ms: performance.now() - t0, body }
        p.rest.push(r)
        return r
      } catch (error) {
        const r = { ok: false, path, ms: performance.now() - t0, error: String(error?.message ?? error) }
        p.rest.push(r)
        return r
      }
    }
    p.socketProbe = (path = '/events', ms = 4000) =>
      new Promise(resolve => {
        const frames = []
        const off = ctx.socket(path, data => frames.push(data))
        setTimeout(() => {
          off()
          resolve({ frames })
        }, ms)
      })

    // 09: colour.
    p.setColor = (storedId, color) => host.sessions.setColor(storedId, color)
    p.snapshotState = snapshotState

    // 14: visible contributions.
    ctx.register({ id: 'chip', area: 'statusBar.right', order: 5, render: () => jsx(Chip, {}) })
    ctx.register({ id: 'route', area: ROUTES_AREA, data: { path: '/cf-spike' }, render: () => jsx(Page, {}) })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/cf-spike', label: 'CF Spike', codicon: 'beaker' },
    })
  },
}
