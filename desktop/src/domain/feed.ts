// The feed reducer (C9, desktop half): turns host.state snapshots, host events, the Python half's
// broadcasts and the session.active_list poll into per-session SIGNALS. Semantics pinned by the
// contract: busy comes only from host busy state (per-runtime `busy` or a `busyBySession` map that
// REPLACES the set); message.start alone never makes a session busy; while the gateway is not open
// a session carries `offline` and never `busy`; `failed` is sticky until the next message.start of
// that session; `unseen` = a turn completed while another session was focused, cleared by focusing;
// a needs-you request clears on its own resolve or the session's message.complete. Runtime ids are
// mapped to stored ids from session.info, state-line stored ids and the focused pair; message.*
// for an unmapped runtime is buffered, in order, and applied when the mapping arrives.
// Ported in structure from origin/agent/tori/cf2909-d2-core-state packages/core/domain/state-desktop.ts
// (per-runtime busy, focused-pair learning, buffered message.*), extended with the C9 signals.
// Pure: reduceFeed never mutates its model, garbage input is ignored, never thrown.
import type { Signal } from './types.ts'

export interface FeedInput {
  kind: string
  t: number
  session?: string | null
  payload?: Record<string, unknown> | null
}

export interface SessionRec {
  failed: boolean
  unseen: boolean
  needsYou: string[]          // open request ids, sorted
  pollStatus: string | null   // last active_list status ('waiting' is the one that matters)
}

export interface FeedModel {
  gateway: string | null
  focusedStored: string | null
  storedOf: Record<string, string>      // runtime id -> stored id
  busyRt: Record<string, boolean>       // runtime-keyed busy, per the latest snapshot
  toolsRt: Record<string, string[]>     // runtime-keyed open tool calls
  compactRt: Record<string, boolean>    // runtime-keyed compacting
  subRt: Record<string, number>         // runtime-keyed running subagents
  sessions: Record<string, SessionRec>  // stored-keyed per-session record
  buffered: Record<string, FeedInput[]> // runtime-keyed message.* waiting for a mapping
  healthOk: boolean | null
  pluginSeen: boolean
}

export const POLL_INTERVAL_MS = 5000
const NEEDS_YOU = 'plugin.cuttlefish-theme.needs_you'
const PLUGIN_ERROR = 'plugin.cuttlefish-theme.error'
const BUFFER_CAP = 64

export function initialFeed(): FeedModel {
  return {
    gateway: null, focusedStored: null, storedOf: {}, busyRt: {}, toolsRt: {}, compactRt: {},
    subRt: {}, sessions: {}, buffered: {}, healthOk: null, pluginSeen: false,
  }
}

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** Key names that can smuggle a read or write onto a shared prototype: never keys of ours. */
const DANGEROUS = new Set(['__proto__', 'constructor', 'prototype'])

/** An id fit to be a key of one of our records (a dangerous name is no id at all). */
const idOk = (v: unknown): v is string => isStr(v) && !DANGEROUS.has(v)

/** Own-property read: a dangerous name never reaches a prototype through us. */
function own<V>(rec: Record<string, V>, key: string): V | undefined {
  return DANGEROUS.has(key) || !Object.hasOwn(rec, key) ? undefined : rec[key]
}

function put<V>(rec: Record<string, V>, key: string, value: V): Record<string, V> {
  if (DANGEROUS.has(key)) return rec
  return { ...rec, [key]: value }
}
function del<V>(rec: Record<string, V>, key: string): Record<string, V> {
  if (!Object.hasOwn(rec, key)) return rec
  const out = { ...rec }
  delete out[key]
  return out
}
function session(m: FeedModel, stored: string): SessionRec {
  return own(m.sessions, stored) ?? { failed: false, unseen: false, needsYou: [], pollStatus: null }
}

/** Learn runtime -> stored and apply whatever was buffered for that runtime, in order. */
function learn(model: FeedModel, rt: string, stored: string): FeedModel {
  if (!idOk(rt) || !idOk(stored)) return model
  let m: FeedModel = own(model.storedOf, rt) === stored
    ? model
    : { ...model, storedOf: put(model.storedOf, rt, stored), sessions: put(model.sessions, stored, session(model, stored)) }
  const queue = own(model.buffered, rt) ?? []
  if (queue.length === 0) return m
  m = { ...m, buffered: del(m.buffered, rt) }
  for (const q of queue) m = applyStored(m, q.kind, rt, stored, isRec(q.payload) ? q.payload : {})
  return m
}

/** The host's two focus atoms move one after the other, so a snapshot can carry a MIXED pair (the old runtime id
 *  with the new stored id, or the reverse). A pair is learned only when it contradicts nothing known: its runtime
 *  id is unmapped or already maps to that stored id, and its stored id has no other runtime mapped. Anything else is
 *  a transient; session.info / the active_list poll carry the authoritative mapping. */
function learnFocusedPair(m: FeedModel, rt: string, stored: string): FeedModel {
  if (!idOk(rt) || !idOk(stored)) return m
  const mapped = own(m.storedOf, rt)
  if (mapped !== undefined) return m
  const other = Object.keys(m.storedOf).some(r => m.storedOf[r] === stored)
  return other ? m : learn(m, rt, stored)
}

/** A turn's end closes every tool call of that runtime (a killed backend sends no tool.complete). */
function turnBoundary(m: FeedModel, rt: string, kind: string): FeedModel {
  let next = m
  if (own(next.toolsRt, rt)?.length) next = { ...next, toolsRt: put(next.toolsRt, rt, []) }
  if (own(next.compactRt, rt)) next = { ...next, compactRt: put(next.compactRt, rt, false) }
  if (kind === 'message.start' && (own(next.subRt, rt) ?? 0) > 0) next = { ...next, subRt: put(next.subRt, rt, 0) }
  return next
}

/** Apply a message.* event to its STORED session (called with the mapping known or learned). */
function applyStored(m: FeedModel, kind: string, rt: string, stored: string, p: Record<string, unknown>): FeedModel {
  let next = turnBoundary(m, rt, kind)
  const rec = session(next, stored)
  if (kind === 'message.start') {
    if (rec.failed || own(next.sessions, stored) === undefined) next = { ...next, sessions: put(next.sessions, stored, { ...rec, failed: false }) }
    return next
  }
  const failed = p.status === 'error' ? true : rec.failed
  const unseen = p.status === 'complete' && next.focusedStored !== stored ? true : rec.unseen
  const needsYou = rec.needsYou.length > 0 ? [] : rec.needsYou
  return { ...next, sessions: put(next.sessions, stored, { ...rec, failed, unseen, needsYou }) }
}

/** A runtime-keyed message.* event, buffered when its runtime id has no mapping yet. */
function applyRuntime(m: FeedModel, kind: string, rt: string, p: Record<string, unknown>, t: number): FeedModel {
  if (!idOk(rt)) return m
  const withBoundary = turnBoundary(m, rt, kind)
  const stored = own(withBoundary.storedOf, rt)
  if (stored !== undefined) return applyStored(withBoundary, kind, rt, stored, p)
  const queue = own(withBoundary.buffered, rt) ?? []
  if (queue.length >= BUFFER_CAP) return withBoundary
  return { ...withBoundary, buffered: put(withBoundary.buffered, rt, [...queue, { kind, t, session: rt, payload: p }]) }
}

function reduceState(m: FeedModel, input: FeedInput, p: Record<string, unknown>): FeedModel {
  let next = m
  if (isStr(p.gateway)) next = { ...next, gateway: p.gateway }
  if (isStr(p.focused_stored_session_id) && isStr(p.focused_session_id)) {
    next = learnFocusedPair(next, p.focused_session_id, p.focused_stored_session_id)
  }
  if (isStr(input.session) && isStr(p.stored_session_id)) next = learn(next, input.session, p.stored_session_id)
  next = { ...next, busyRt: busySnapshot(next.busyRt, input, p) }
  return focus(next, p)
}

/** The busy set of a state snapshot: a `busyBySession` map REPLACES it, a plain `busy` flag merges. */
function busySnapshot(current: Record<string, boolean>, input: FeedInput, p: Record<string, unknown>): Record<string, boolean> {
  if (isRec(p.busyBySession)) {
    const map: Record<string, boolean> = {}
    for (const [rt, b] of Object.entries(p.busyBySession)) if (!DANGEROUS.has(rt)) map[rt] = b === true
    return map
  }
  if (typeof p.busy === 'boolean' && isStr(input.session)) return put(current, input.session, p.busy)
  return current
}

/** Resolve the focused session of a state snapshot; focusing a session clears its `unseen`. */
function focus(m: FeedModel, p: Record<string, unknown>): FeedModel {
  let stored: string | null = null
  if (idOk(p.focused_stored_session_id)) stored = p.focused_stored_session_id
  else if (idOk(p.focused_session_id)) stored = own(m.storedOf, p.focused_session_id) ?? null
  // Ctrl+N: a focused runtime with an explicit null stored id and no mapping is a new empty chat — nothing stored is focused.
  if (stored === null && p.focused_stored_session_id === null && idOk(p.focused_session_id)) {
    return m.focusedStored === null ? m : { ...m, focusedStored: null }
  }
  if (stored === null || m.focusedStored === stored) return m
  const rec = session(m, stored)
  return { ...m, focusedStored: stored, sessions: put(m.sessions, stored, { ...rec, unseen: false }) }
}

function reduceTool(m: FeedModel, input: FeedInput, p: Record<string, unknown>, start: boolean): FeedModel {
  const rt = input.session
  if (!idOk(rt)) return m
  const id = isStr(p.tool_call_id) ? p.tool_call_id : ''
  const open = own(m.toolsRt, rt) ?? []
  const next = start ? (open.includes(id) ? open : [...open, id].sort()) : open.filter(x => x !== id)
  return { ...m, toolsRt: put(m.toolsRt, rt, next) }
}

function reducePluginNeedsYou(m: FeedModel, p: Record<string, unknown>): FeedModel {
  const stored = p.session_id
  if (!idOk(stored)) return m
  const rec = session(m, stored)
  const id = isStr(p.request_id) ? p.request_id : ''
  const open = p.active === false ? rec.needsYou.filter(x => x !== id) : (rec.needsYou.includes(id) ? rec.needsYou : [...rec.needsYou, id].sort())
  return { ...m, pluginSeen: true, sessions: put(m.sessions, stored, { ...rec, needsYou: open }) }
}

function reducePluginError(m: FeedModel, p: Record<string, unknown>): FeedModel {
  const stored = p.session_id
  if (!idOk(stored)) return m
  const rec = session(m, stored)
  const failed = p.retryable === true ? rec.failed : true
  return { ...m, pluginSeen: true, sessions: put(m.sessions, stored, { ...rec, failed }) }
}

/** session.active_list poll: learns runtime -> stored and carries the only poll-driven signal. */
function reduceActiveList(m: FeedModel, p: Record<string, unknown>): FeedModel {
  const list = p.sessions
  if (!Array.isArray(list)) return m
  const seen = new Set<string>()
  const next = list.reduce(applyListEntry, m)
  for (const e of list) if (isRec(e) && idOk(e.session_key)) seen.add(e.session_key)
  return clearAbsentPollStatus(next, seen)
}

function applyListEntry(m: FeedModel, e: unknown): FeedModel {
  if (!isRec(e) || !idOk(e.id) || !idOk(e.session_key)) return m
  const next = learn(m, e.id, e.session_key)
  const rec = session(next, e.session_key)
  return { ...next, sessions: put(next.sessions, e.session_key, { ...rec, pollStatus: isStr(e.status) ? e.status : null }) }
}

/** A session absent from the poll's answer no longer carries a poll status. */
function clearAbsentPollStatus(m: FeedModel, seen: Set<string>): FeedModel {
  let next = m
  for (const stored of Object.keys(next.sessions)) {
    if (!seen.has(stored) && next.sessions[stored].pollStatus !== null) {
      next = { ...next, sessions: put(next.sessions, stored, { ...next.sessions[stored], pollStatus: null }) }
    }
  }
  return next
}

function reduceStatusUpdate(m: FeedModel, input: FeedInput, p: Record<string, unknown>): FeedModel {
  if (!idOk(input.session) || p.kind !== 'compacting') return m
  return { ...m, compactRt: put(m.compactRt, input.session, true) }
}

function reduceSubagent(m: FeedModel, input: FeedInput, start: boolean): FeedModel {
  const rt = input.session
  if (!idOk(rt)) return m
  const n = own(m.subRt, rt) ?? 0
  return { ...m, subRt: put(m.subRt, rt, start ? n + 1 : Math.max(0, n - 1)) }
}

type Reducer = (m: FeedModel, input: FeedInput, p: Record<string, unknown>) => FeedModel

const reduceSessionInfo: Reducer = (m, input, p) =>
  idOk(input.session) && isStr(p.stored_session_id) ? learn(m, input.session, p.stored_session_id) : m

const reduceMessage: Reducer = (m, input, p) =>
  idOk(input.session) ? applyRuntime(m, input.kind, input.session, p, input.t) : m

const reduceHealth: Reducer = (m, _i, p) => (m.healthOk === (p.ok === true) ? m : { ...m, healthOk: p.ok === true })

/** One reducer per event kind; an unknown kind (or garbage) falls through to the identity. */
const REDUCERS: Record<string, Reducer> = {
  'state': reduceState,
  'session.info': reduceSessionInfo,
  'message.start': reduceMessage,
  'message.complete': reduceMessage,
  'tool.start': (m, i, p) => reduceTool(m, i, p, true),
  'tool.complete': (m, i, p) => reduceTool(m, i, p, false),
  'status.update': reduceStatusUpdate,
  'subagent.start': (m, i) => reduceSubagent(m, i, true),
  'subagent.complete': (m, i) => reduceSubagent(m, i, false),
  [NEEDS_YOU]: (m, _i, p) => reducePluginNeedsYou(m, p),
  [PLUGIN_ERROR]: (m, _i, p) => reducePluginError(m, p),
  'python.health': reduceHealth,
  'active_list': (m, _i, p) => reduceActiveList(m, p),
}

/** One event in. Unknown kinds, missing sessions and garbage payloads are ignored, never thrown. */
export function reduceFeed(model: FeedModel, input: FeedInput): FeedModel {
  if (!isRec(input)) return model
  const reducer = typeof input.kind === 'string' && Object.hasOwn(REDUCERS, input.kind) ? REDUCERS[input.kind] : undefined
  return reducer ? reducer(model, input, isRec(input.payload) ? input.payload : {}) : model
}

/** Every stored id the model can attribute state to, sorted. */
export function knownSessions(model: FeedModel): string[] {
  return Object.keys(model.sessions).sort()
}

interface SignalCtx {
  rts: string[]
  rec: SessionRec
  open: boolean
  busyRt: Record<string, boolean>
  toolsRt: Record<string, string[]>
  compactRt: Record<string, boolean>
  subRt: Record<string, number>
}

/** Each signal as one predicate over the session's context, in priority order. */
const SIGNAL_RULES: readonly [Signal, (c: SignalCtx) => boolean][] = [
  ['busy', c => c.open && c.rts.some(rt => own(c.busyRt, rt) === true)],
  ['offline', c => !c.open],
  ['tool', c => c.rts.some(rt => (own(c.toolsRt, rt) ?? []).length > 0)],
  ['needs_input', c => c.rec.needsYou.length > 0 || c.rec.pollStatus === 'waiting'],
  ['failed', c => c.rec.failed],
  ['unseen', c => c.rec.unseen],
  ['compacting', c => c.rts.some(rt => own(c.compactRt, rt) === true)],
  ['subagents', c => c.rts.reduce((n, rt) => n + (own(c.subRt, rt) ?? 0), 0) > 0],
]

/** The signals of one stored session (an unknown session carries none). */
export function signalsOf(model: FeedModel, storedId: string): Set<Signal> {
  const out = new Set<Signal>()
  const rec = own(model.sessions, storedId)
  if (!rec) return out
  const ctx: SignalCtx = {
    rts: Object.keys(model.storedOf).filter(rt => model.storedOf[rt] === storedId),
    rec, open: model.gateway === 'open',
    busyRt: model.busyRt, toolsRt: model.toolsRt, compactRt: model.compactRt, subRt: model.subRt,
  }
  for (const [signal, on] of SIGNAL_RULES) if (on(ctx)) out.add(signal)
  if (!out.has('busy')) out.add('idle')
  return out
}

/** Poll session.active_list only while the gateway is open and the Python half is off/unknown. */
export function pollPlan(model: FeedModel, nowMs: number): { pollActiveList: boolean; intervalMs: number } {
  void nowMs
  const pythonOn = model.pluginSeen || model.healthOk === true
  return { pollActiveList: model.gateway === 'open' && !pythonOn, intervalMs: POLL_INTERVAL_MS }
}
