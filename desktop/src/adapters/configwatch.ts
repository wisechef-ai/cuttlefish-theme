// The config watch and the Python-half poll (C5/C9), as one wiring over injected
// doors — pure decision logic lives in the domain (configPlan, pollPlan).
//   - the mtime watch fetches /config exactly when the file's mtime CHANGES,
//     first sight included, with an early kick so a config edited before the
//     first interval still counts as a change (never less than two sightings);
//   - the poll probes /health first on every tick and asks session.active_list
//     only while the domain's pollPlan wants it (the gateway open and the Python
//     half off/unknown) — the Python half's own broadcasts stop the polling.
// Everything survives a throw: a failed fetch keeps the last settings, a failed
// poll is one missed poll, and dispose stops every timer.
import { configPlan, initialConfigWatch, POLL_INTERVAL_MS, type ConfigWatch, type FeedInput } from '../domain/index.ts'

/** The first /config fetch happens promptly, not one watch interval in. */
export const FIRST_WATCH_MS = 50
/** The mtime watch cadence (the SDK floors plugin intervals at 2 s). */
export const WATCH_MS = 2000

export interface WatchDoors {
  request(method: string, params?: unknown): Promise<unknown>
  rest(path: string): Promise<unknown>
  setTimeout(fn: () => void, ms: number): () => void
  setInterval(fn: () => void, ms: number): () => void
  now?(): number
}

export interface WatchHooks {
  onFeed(input: FeedInput): void
  onSettings(config: unknown): void
  pollWanted(): boolean
}

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** Wire the watch + poll over `doors`. Returns the stop function (idempotent). */
export function wireWatch(doors: WatchDoors, hooks: WatchHooks): () => void {
  let watch: ConfigWatch = initialConfigWatch()
  const stopped: (() => void)[] = []
  let live = true

  const mtimeTick = async () => {
    try {
      const answer = await doors.request('config.get', { key: 'mtime' })
      const plan = configPlan(watch, isRec(answer) ? (answer.mtime as number | string | null | undefined) ?? null : null)
      watch = plan.next
      if (plan.refetch) hooks.onSettings(await doors.rest('/config'))
    } catch {
      // an unreadable mtime or a failed fetch keeps the last settings
    }
  }

  const pollTick = async () => {
    const t = doors.now?.() ?? 0
    let ok = false
    try {
      await doors.rest('/health')
      ok = true
    } catch {
      ok = false
    }
    hooks.onFeed({ kind: 'python.health', t, session: null, payload: { ok } })
    try {
      if (!hooks.pollWanted()) return
      const list = await doors.request('session.active_list')
      if (isRec(list)) hooks.onFeed({ kind: 'active_list', t, session: null, payload: list })
    } catch {
      // one missed poll never kills the watch
    }
  }

  stopped.push(doors.setTimeout(() => { void mtimeTick() }, FIRST_WATCH_MS))
  stopped.push(doors.setInterval(() => { void mtimeTick() }, WATCH_MS))
  stopped.push(doors.setInterval(() => { void pollTick() }, POLL_INTERVAL_MS))

  return () => {
    if (!live) return
    live = false
    for (const stop of stopped) stop()
  }
}
