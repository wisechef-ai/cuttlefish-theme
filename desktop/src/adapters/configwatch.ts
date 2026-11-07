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

/** The mtime an answer carries, or null when the answer is not an object. */
function mtimeOf(answer: unknown): number | string | null {
  if (!isRec(answer)) return null
  return (answer.mtime as number | string | null | undefined) ?? null
}

/** One mtime sighting: fetch /config exactly when the mtime CHANGED (first sight included). */
async function mtimeTick(doors: WatchDoors, hooks: WatchHooks, cell: { watch: ConfigWatch }): Promise<void> {
  try {
    const plan = configPlan(cell.watch, mtimeOf(await doors.request('config.get', { key: 'mtime' })))
    cell.watch = plan.next
    if (plan.refetch) hooks.onSettings(await doors.rest('/config'))
  } catch {
    // an unreadable mtime or a failed fetch keeps the last settings
  }
}

/** Is the Python half's health route answering? A throw means "no", never "stop". */
async function healthOk(doors: WatchDoors): Promise<boolean> {
  try {
    await doors.rest('/health')
    return true
  } catch {
    return false
  }
}

/** One poll tick: report the health probe, then ask for the list only while the domain wants it. */
async function pollTick(doors: WatchDoors, hooks: WatchHooks): Promise<void> {
  const t = doors.now?.() ?? 0
  hooks.onFeed({ kind: 'python.health', t, session: null, payload: { ok: await healthOk(doors) } })
  try {
    if (!hooks.pollWanted()) return
    const list = await doors.request('session.active_list')
    if (isRec(list)) hooks.onFeed({ kind: 'active_list', t, session: null, payload: list })
  } catch {
    // one missed poll never kills the watch
  }
}

/** Wire the watch + poll over `doors`. Returns the stop function (idempotent). */
export function wireWatch(doors: WatchDoors, hooks: WatchHooks): () => void {
  const cell: { watch: ConfigWatch } = { watch: initialConfigWatch() }
  const stopped: (() => void)[] = []
  const mtime = (): void => { void mtimeTick(doors, hooks, cell) }
  const poll = (): void => { void pollTick(doors, hooks) }
  stopped.push(doors.setTimeout(mtime, FIRST_WATCH_MS))
  stopped.push(doors.setInterval(mtime, WATCH_MS))
  stopped.push(doors.setInterval(poll, POLL_INTERVAL_MS))
  let live = true
  return () => {
    if (!live) return
    live = false
    for (const stop of stopped) stop()
  }
}
