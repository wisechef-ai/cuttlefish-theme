// The host→feed mapping (C9): host.state atoms and gateway events become the
// FeedInput kinds the domain's reducer speaks, exactly as contract/README.md
// §Feed inputs pins them. Garbage (an unmodelled type, a missing session id, a
// non-object) maps to null — the adapter lane never throws at a host boundary.
import type { FeedInput } from '../domain/index.ts'

/** A minimal read-only atom, as host.state provides (and the fakes model). */
export interface Atom<T> {
  get(): T
}

export interface StateAtoms {
  activeSessionId: Atom<string | null>
  busy: Atom<boolean>
  busyBySession: Atom<Record<string, boolean>>
  focusedSessionId: Atom<string | null>
  focusedStoredSessionId: Atom<string | null>
  gateway: Atom<string>
}

/** Kinds that carry their target in `session_id` and are meaningless without one. */
const SESSION_KINDS: ReadonlySet<string> = new Set([
  'session.info', 'message.start', 'message.complete', 'tool.start', 'tool.complete',
  'status.update', 'subagent.start', 'subagent.complete',
])

/** Every host event kind the plugin listens for (the plugin.* pair included). */
export const FEED_EVENT_KINDS: ReadonlySet<string> = new Set([
  ...SESSION_KINDS,
  'plugin.cuttlefish-theme.needs_you',
  'plugin.cuttlefish-theme.error',
  'python.health',
  'active_list',
])

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** One gateway event to its feed input, or null when it is not ours. */
export function eventToFeed(event: unknown, t: number): FeedInput | null {
  if (!isRec(event)) return null
  const { type, session_id, payload } = event
  if (typeof type !== 'string' || !FEED_EVENT_KINDS.has(type)) return null
  const session = isStr(session_id) ? session_id : null
  if (SESSION_KINDS.has(type) && session === null) return null
  return { kind: type, t, session, payload: isRec(payload) ? payload : null }
}

/** The host.state atoms as one `state` feed input; absent doors stay absent.
 *  The host's `busyBySession` is authoritative — a present map REPLACES the busy
 *  set in the domain, and an EMPTY one legitimately means "nobody is busy", so it
 *  is forwarded (else a dropped session entry would leave a stale "working").
 *  The one exception: an empty map beside a busy plain flag cannot come from the
 *  real host (its `busy` is a subset of the map) — only from a flag-only source —
 *  so the map is withheld there and the flag speaks. */
export function stateSnapshot(atoms: StateAtoms, t: number): FeedInput {
  const payload: Record<string, unknown> = {}
  const gateway = atoms.gateway.get()
  if (isStr(gateway)) payload.gateway = gateway
  const busy = atoms.busy.get()
  if (typeof busy === 'boolean') payload.busy = busy
  const bySession = atoms.busyBySession.get()
  if (isRec(bySession) && (busy !== true || Object.keys(bySession).length > 0)) payload.busyBySession = { ...bySession }
  const focused = atoms.focusedSessionId.get()
  if (isStr(focused)) payload.focused_session_id = focused
  const focusedStored = atoms.focusedStoredSessionId.get()
  if (isStr(focusedStored)) payload.focused_stored_session_id = focusedStored
  else if (focusedStored === null && isStr(focused)) payload.focused_stored_session_id = null // a new empty chat (Ctrl+N)
  const active = atoms.activeSessionId.get()
  return { kind: 'state', t, session: isStr(active) ? active : null, payload }
}
