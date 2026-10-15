// State reducer for the desktop host, CONTRACT.md §3 (spike 07). Pure, keyed by STORED session id.
// The host speaks RUNTIME ids (busyBySession, message.*); only `session.info` carries both. Events for a
// runtime id with no mapping yet are buffered, in order, and applied the moment the mapping arrives.
import type { State } from './state-hook.ts';

export interface DesktopInput {
  /** state | session.info | message.start | message.complete | dot (| busy: internal form of one busyBySession entry). */
  kind: string;
  /** Runtime id for state(busy)/session.info/message.*; STORED id for dot. */
  session?: string | null;
  payload?: {
    gateway?: string | null;
    busyBySession?: Readonly<Record<string, boolean>> | null;
    busy?: boolean | null;
    stored_session_id?: string | null;
    stored_id?: string | null;
    status?: string | null;
    label?: string | null;
    [k: string]: unknown;
  } | null;
}

export interface DesktopModel {
  /** null until the first snapshot that carries it (= unknown). */
  readonly gateway: string | null;
  readonly stored_of: Readonly<Record<string, string>>;
  readonly busy: Readonly<Record<string, boolean>>;
  readonly fault: Readonly<Record<string, boolean>>;
  readonly needs_input: Readonly<Record<string, boolean>>;
  /** Runtime-id keyed inputs waiting for a mapping, in arrival order. */
  readonly buffered: Readonly<Record<string, readonly DesktopInput[]>>;
}

export function initial(): DesktopModel {
  return { gateway: null, stored_of: {}, busy: {}, fault: {}, needs_input: {}, buffered: {} };
}

/** i18n strings core's SessionStatusDot puts in span[role=status] aria-label (spike 07; idle dots have no label). */
export const CORE_DOT_LABELS = { working: 'Session running', needsYou: 'Needs your input' } as const;

const set = <V>(rec: Readonly<Record<string, V>>, k: string, v: V): Readonly<Record<string, V>> => ({ ...rec, [k]: v });

function applyStored(m: DesktopModel, kind: string, stored: string, p: NonNullable<DesktopInput['payload']>): DesktopModel {
  switch (kind) {
    case 'busy': return { ...m, busy: set(m.busy, stored, p.busy === true) };
    case 'message.start': return { ...m, fault: set(m.fault, stored, false) };
    case 'message.complete': return p.status === 'error' ? { ...m, fault: set(m.fault, stored, true) } : m;
    default: return m;
  }
}

/** Apply a runtime-keyed input, or buffer it when its runtime id is not mapped yet. */
function applyRuntime(m: DesktopModel, kind: string, rt: string, p: NonNullable<DesktopInput['payload']>): DesktopModel {
  const stored = m.stored_of[rt];
  if (stored !== undefined) return applyStored(m, kind, stored, p);
  const queue = m.buffered[rt] ?? [];
  return { ...m, buffered: set(m.buffered, rt, [...queue, { kind, session: rt, payload: p }]) };
}

export function reduce(model: DesktopModel, input: DesktopInput): DesktopModel {
  const p = input.payload ?? {};
  switch (input.kind) {
    case 'state': {
      let m: DesktopModel = typeof p.gateway === 'string' ? { ...model, gateway: p.gateway } : model;
      if (p.busyBySession) for (const rt of Object.keys(p.busyBySession).sort()) m = applyRuntime(m, 'busy', rt, { busy: p.busyBySession[rt] });
      else if (typeof p.busy === 'boolean' && input.session) m = applyRuntime(m, 'busy', input.session, { busy: p.busy });
      return m;
    }
    case 'session.info': {
      const stored = p.stored_session_id;
      const rt = input.session;
      if (!rt || !stored) return model;
      const { [rt]: queue = [], ...rest } = model.buffered;
      let m: DesktopModel = { ...model, stored_of: set(model.stored_of, rt, stored), buffered: rest };
      for (const q of queue) m = applyStored(m, q.kind, stored, q.payload ?? {});
      return m;
    }
    case 'message.start':
    case 'message.complete':
      return input.session ? applyRuntime(model, input.kind, input.session, p) : model;
    case 'dot': {
      const stored = input.session ?? p.stored_session_id ?? p.stored_id;
      if (!stored) return model;
      return { ...model, needs_input: set(model.needs_input, stored, p.label === CORE_DOT_LABELS.needsYou) };
    }
    default:
      return model;
  }
}

/** Every stored id the model can attribute state to, sorted. */
export function storedIds(model: DesktopModel): string[] {
  return [...new Set([...Object.values(model.stored_of), ...Object.keys(model.needs_input)])].sort();
}

/** unknown if the gateway is not open, then needs-you, fault, working, idle. No review on desktop. */
export function resolve(model: DesktopModel, stored: string): State {
  if (model.gateway !== 'open') return 'unknown';
  if (model.needs_input[stored]) return 'needs-you';
  if (model.fault[stored]) return 'fault';
  if (model.busy[stored]) return 'working';
  return 'idle';
}

/** What core's dot means; null for a label we do not model (e.g. a background-task dot). */
function coreState(label: string): State | null {
  if (label === '') return 'idle';
  if (label === CORE_DOT_LABELS.working) return 'working';
  if (label === CORE_DOT_LABELS.needsYou) return 'needs-you';
  return null;
}

export type Parity = 'match' | `allowed:${string}` | 'MISMATCH';

/** Compare our resolved state with what core's dot shows (aria-label, or null/'' for the unlabelled idle dot). */
export function classifyParity(ours: State, coreLabel: string | null | undefined): Parity {
  const core = coreState(coreLabel ?? '');
  if (core !== null && ours === core) return 'match';
  if (ours === 'unknown') return 'allowed:gateway-not-open';          // core shows stale busy for up to ~26 s after a kill
  if (ours === 'fault' && core === 'idle') return 'allowed:fault-not-painted';   // core paints no fault dot
  return 'MISMATCH';
}
