// State reducer for the TUI hook bus, CONTRACT.md §2 (spike 06). Pure: `reduce(model, event) -> model`,
// `resolve(model, now) -> state`. No clock reads (time is the event's `t` or the caller's `now`), no I/O.
// One model per LINEAGE ROOT; the reducer never walks lineage, callers pass the root.

export type State = 'idle' | 'thinking' | 'tool' | 'review' | 'needs-you' | 'fault' | 'unknown';
export const STATES: readonly State[] = ['idle', 'thinking', 'tool', 'review', 'needs-you', 'fault', 'unknown'];

/** Capability flags, one per host: does the host's event stream tell a tool from the model thinking (CONTRACT §2/§3)?
 *  A surface with no tool signal maps busy -> thinking and `hermes cuttlefish doctor` says so. */
export const TOOL_SIGNAL = { tui: true, desktop: true } as const;

/** Silence longer than this (seconds) makes a session unknown. The bus heartbeats every 5 s while the owner lives. */
export const STALE_S = 20.0;
/** `pre_verify` holds `review` at least this long (it fires ~100 ms before the turn ends). */
export const REVIEW_DWELL_S = 0.6;

export interface HookPayload {
  tool_name?: string | null;
  tool_call_id?: string | null;
  session_key?: string | null;
  pattern_key?: string | null;
  completed?: boolean | null;
  bound?: boolean | null;
  [k: string]: unknown;
}
/** One normalised event for one lineage root: `kind` is a hook name or heartbeat | pid_dead | binding. */
export interface HookEvent { t: number; kind: string; payload?: HookPayload | null }

export interface HookModel {
  readonly in_turn: boolean;
  /** Open non-clarify tool calls (`tool:<tool_call_id>`), sorted; empty outside a tool. */
  readonly tools: readonly string[];
  /** Open asks, sorted (so a model serialises canonically): `clarify:<id>` and `approval:<id>`. */
  readonly pending: readonly string[];
  readonly fault: boolean;
  readonly review_until: number | null;
  readonly finalized: boolean;
  /** Time of the last event of any kind; null until the first one (nothing seen = unknown). */
  readonly last_seen: number | null;
  readonly bound: boolean;
  readonly pid_alive: boolean | null;
}

export function initial(): HookModel {
  return { in_turn: false, tools: [], pending: [], fault: false, review_until: null, finalized: false, last_seen: null, bound: true, pid_alive: null };
}

const add = (xs: readonly string[], k: string): readonly string[] => (xs.includes(k) ? xs : [...xs, k].sort());
const drop = (xs: readonly string[], k: string): readonly string[] => xs.filter(x => x !== k);

function toolKey(p: HookPayload): string { return `tool:${p.tool_call_id ?? ''}`; }
function clarifyKey(p: HookPayload): string { return `clarify:${p.tool_call_id ?? ''}`; }
function approvalKey(p: HookPayload): string {
  return `approval:${p.tool_call_id ? p.tool_call_id : `${p.session_key ?? ''}/${p.pattern_key ?? ''}`}`;
}

export function reduce(model: HookModel, ev: HookEvent): HookModel {
  const p: HookPayload = ev.payload ?? {};
  // every event from the session is proof of life
  const m: HookModel = { ...model, last_seen: ev.t };
  switch (ev.kind) {
    case 'on_session_reset':
      return { ...m, in_turn: false, tools: [], pending: [], fault: false, review_until: null, finalized: false, pid_alive: null };
    case 'pre_llm_call':
      return { ...m, in_turn: true, tools: [], fault: false, finalized: false };
    case 'post_llm_call':
      return { ...m, tools: [], fault: false };
    case 'on_session_end':
      return { ...m, in_turn: false, tools: [], pending: [], fault: p.completed === true ? false : m.fault };
    case 'on_session_finalize':
      return { ...m, finalized: true, in_turn: false, tools: [], pending: [] };
    case 'pre_tool_call':
      return p.tool_name === 'clarify' ? { ...m, pending: add(m.pending, clarifyKey(p)) } : { ...m, tools: add(m.tools, toolKey(p)) };
    case 'post_tool_call':
      return p.tool_name === 'clarify' ? { ...m, pending: drop(m.pending, clarifyKey(p)) } : { ...m, tools: drop(m.tools, toolKey(p)) };
    case 'pre_approval_request':
      return { ...m, pending: add(m.pending, approvalKey(p)) };
    case 'post_approval_response':
      return { ...m, pending: drop(m.pending, approvalKey(p)) };
    case 'api_request_error':
      // Only a NON-retryable error is sticky fault (CONTEXT-D2 §0). retryable === true is a transient
      // failure the provider is still retrying: proof of life only. Missing/malformed flag => fatal.
      return p.retryable === true ? m : { ...m, fault: true };
    case 'pre_verify':
      return { ...m, review_until: ev.t + REVIEW_DWELL_S };
    case 'heartbeat':
      return { ...m, pid_alive: true };
    case 'pid_dead':
      return { ...m, pid_alive: false };
    case 'binding':
      return { ...m, bound: p.bound === true };
    default:
      return m;   // on_session_start and anything unrecognised: proof of life only
  }
}

/** First match wins. "Turn ended" is never needs-you, and stale is never the last known state. */
export function resolve(model: HookModel, now: number): State {
  if (model.last_seen === null || model.finalized || model.pid_alive === false || model.bound === false || now - model.last_seen > STALE_S) return 'unknown';
  if (model.pending.length > 0) return 'needs-you';
  if (model.fault) return 'fault';
  if (model.in_turn) return model.tools.length > 0 ? 'tool' : 'thinking';
  if (model.review_until !== null && now < model.review_until) return 'review';
  return 'idle';
}

/** Models for many sessions, keyed by lineage root. */
export type HookModels = Readonly<Record<string, HookModel>>;
export function reduceKeyed(models: HookModels, lineageRoot: string, ev: HookEvent): HookModels {
  return { ...models, [lineageRoot]: reduce(models[lineageRoot] ?? initial(), ev) };
}

/** `since` tracker: the time of the last change of the RESOLVED value (observed at events and ticks). */
export interface Tracker { readonly state: State | null; readonly since: number }
export const trackInit = (): Tracker => ({ state: null, since: 0 });
export function trackStep(tr: Tracker, state: State, t: number): Tracker {
  return tr.state === state ? tr : { state, since: t };
}
