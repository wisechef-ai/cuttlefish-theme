// Use-case: replay a recorded trace (CONTRACT.md §4) through the matching state reducer and report, per
// lineage root, the resolved state at every event instant AND at synthetic ticks every `stepS` (so that
// stale -> unknown and the end of the review dwell, which no event announces, are observed). Pure: all
// time comes from the trace. Output is canonical JSON so two runs (or two bundles) diff byte for byte.
import { allocate } from '../domain/identity.ts';
import {
  initial as hookInitial, reduce as hookReduce, resolve as hookResolve, trackInit, trackStep, STALE_S,
  type HookModel, type State, type Tracker,
} from '../domain/state-hook.ts';
import {
  initial as deskInitial, reduce as deskReduce, resolve as deskResolve, storedIds, classifyParity,
  type DesktopInput, type DesktopModel, type Parity,
} from '../domain/state-desktop.ts';

/** The replay keeps ticking this long after the last event, enough to observe the final stale -> unknown. */
export const TAIL_S = STALE_S + 5;

export interface ReplayOptions { stepS?: number }
export interface ReplaySample {
  t: number;
  on: 'event' | 'tick';
  state: State;
  /** Time of the last change of the resolved state, as observed at events and ticks. */
  since: number;
  /** Desktop only, once a core dot has been observed for the session: its label and our parity with it. */
  core?: string;
  parity?: Parity;
  /** Desktop, parity allowed:render-lag only: seconds from our last state change until core's dot agreed. */
  lag_s?: number;
}
export interface ReplayIdentity { slot: number; hue_deg: number; crowded: boolean }
export interface ReplayRoot { profile: string; identity: ReplayIdentity | null; samples: ReplaySample[] }
export interface ReplayResult {
  v: 1;
  name: string;
  host: 'tui' | 'desktop';
  step_s: number;
  /** Lines that carried neither a lineage root nor a session id (never guessed). */
  skipped: number;
  roots: Record<string, ReplayRoot>;
}

// Trace payloads are a whitelist of loosely typed scalars (CONTRACT §4), read field by field; hence `any`.
type Line = { t: number; src: string; kind: string; profile: string; session: string | null; lineage_root: string | null; payload: Record<string, any> };

const HOOK_KINDS_ANY_SRC = new Set(['heartbeat', 'pid_dead', 'binding']);
const DESKTOP_KINDS = new Set(['state', 'session.info', 'message.start', 'message.complete', 'tool.start', 'tool.complete', 'dot']);
const nonBlank = (s: unknown): s is string => typeof s === 'string' && s.trim() !== '';

/** The lineage root of a hook line; the session id stands in only when the trace carries no root. */
function rootKeyOf(l: Line): string | null {
  if (nonBlank(l.lineage_root)) return l.lineage_root;
  if (nonBlank(l.session)) return l.session;
  return null;
}

export function canonicalJson(v: unknown): string {
  // `any`: a recursive walk over arbitrary JSON values.
  const norm = (x: any): any => {
    if (Array.isArray(x)) return x.map(norm);
    if (x && typeof x === 'object') {
      const out: Record<string, unknown> = {};
      for (const k of Object.keys(x).sort()) if (x[k] !== undefined) out[k] = norm(x[k]);
      return out;
    }
    return x;
  };
  return JSON.stringify(norm(v));
}

// `any`: raw parsed trace lines, validated field by field below.
function parseLines(traceLines: readonly (string | object)[]): any[] {
  const out: any[] = [];
  for (const l of traceLines) {
    if (typeof l === 'string') { if (l.trim() !== '') out.push(JSON.parse(l)); } else if (l != null) out.push(l);
  }
  return out;
}

export function replay(traceLines: readonly (string | object)[], opts: ReplayOptions = {}): ReplayResult {
  const stepS = opts.stepS ?? 1;
  if (!(stepS > 0) || !Number.isFinite(stepS)) throw new RangeError(`stepS must be a positive number, got ${stepS}`);
  const objs = parseLines(traceLines);
  const head = objs[0];
  if (!head || head.src !== 'meta' || head.kind !== 'trace') throw new Error('trace has no header line (src "meta", kind "trace")');
  const host: 'tui' | 'desktop' = head.host === 'desktop' ? 'desktop' : 'tui';

  const roots: Record<string, ReplayRoot> = {};
  const trackers: Record<string, Tracker> = {};
  const slotsByProfile: Record<string, number[]> = {};
  let skipped = 0;

  /** First sight of a root: allocate against the other roots of the same profile seen so far, then persist. */
  const ensureRoot = (key: string, profile: string): void => {
    if (roots[key]) return;
    const peers = slotsByProfile[profile] ?? (slotsByProfile[profile] = []);
    const a = allocate(key, peers);
    peers.push(a.slot);
    roots[key] = { profile, identity: { slot: a.slot, hue_deg: Math.round(a.hue_deg * 100) / 100, crowded: a.crowded }, samples: [] };
    trackers[key] = trackInit();
  };

  // ---- host engines: apply(line) returns the root keys the line touched, stateOf resolves one root ----
  const hookModels: Record<string, HookModel> = {};
  const desk: { m: DesktopModel; core: Record<string, string>; dots: Record<string, Array<{ t: number; label: string }>> } = { m: deskInitial(), core: {}, dots: {} };

  const applyHook = (l: Line): string[] => {
    const relevant = l.src === 'hook' || (HOOK_KINDS_ANY_SRC.has(l.kind) && !l.src.startsWith('desktop.'));
    if (!relevant) return [];
    const key = rootKeyOf(l);
    if (key === null) { skipped++; return []; }
    ensureRoot(key, l.profile);
    hookModels[key] = hookReduce(hookModels[key] ?? hookInitial(), { t: l.t, kind: l.kind, payload: l.payload });
    return [key];
  };
  const applyDesktop = (l: Line): string[] => {
    if (!l.src.startsWith('desktop.') || !DESKTOP_KINDS.has(l.kind)) return [];
    const input: DesktopInput = l.kind === 'dot'
      ? { kind: 'dot', session: l.session ?? l.payload.stored_session_id ?? l.payload.stored_id ?? null, payload: l.payload }
      : { kind: l.kind, session: l.session, payload: l.payload };
    desk.m = deskReduce(desk.m, input);
    if (l.kind === 'dot' && input.session) {
      const label = typeof l.payload.label === 'string' ? l.payload.label : '';
      desk.core[input.session] = label;
      (desk.dots[input.session] ??= []).push({ t: l.t, label });
    }
    for (const id of storedIds(desk.m)) ensureRoot(id, l.profile);
    return storedIds(desk.m);
  };
  const apply = host === 'desktop' ? applyDesktop : applyHook;

  const sample = (key: string, t: number, on: 'event' | 'tick'): void => {
    const state = host === 'desktop' ? deskResolve(desk.m, key) : hookResolve(hookModels[key], t);
    const tr = trackStep(trackers[key], state, t);
    trackers[key] = tr;
    const s: ReplaySample = { t, on, state, since: tr.since };
    if (host === 'desktop' && key in desk.core) { s.core = desk.core[key]; s.parity = classifyParity(state, desk.core[key]); }
    roots[key].samples.push(s);
  };

  // ---- normalise, order by time (stable), group lines that share an instant ----
  const lines: Array<{ l: Line; i: number }> = [];
  objs.slice(1).forEach((o, i) => {
    if (!o || o.src === 'meta') return;
    if (typeof o.t !== 'number' || !Number.isFinite(o.t)) throw new Error(`trace line ${i + 2} has no finite "t"`);
    lines.push({ i, l: { t: o.t, src: String(o.src ?? ''), kind: String(o.kind ?? ''), profile: nonBlank(o.profile) ? o.profile : 'default', session: o.session ?? null, lineage_root: o.lineage_root ?? null, payload: o.payload ?? {} } });
  });
  lines.sort((a, b) => a.l.t - b.l.t || a.i - b.i);

  let k = lines.length > 0 ? Math.ceil(lines[0].l.t / stepS) : 0;
  const tickTo = (t: number): void => {
    while (k * stepS <= t) { const tt = k * stepS; for (const key of Object.keys(roots)) sample(key, tt, 'tick'); k++; }
  };
  let lastT = 0;
  for (let a = 0; a < lines.length;) {
    const t = lines[a].l.t;
    let b = a;
    while (b < lines.length && lines[b].l.t === t) b++;
    tickTo(t);                                   // ticks up to and including t see the state BEFORE this instant's events
    const touched = new Set<string>();
    for (let j = a; j < b; j++) for (const key of apply(lines[j].l)) touched.add(key);
    for (const key of [...touched].sort()) sample(key, t, 'event');
    if (touched.size > 0) lastT = t;
    a = b;
  }
  tickTo(lastT + TAIL_S);

  // Render lag (CONTRACT §3): a disagreement is allowed when core's dot agrees (match, or an allowed rule such as fault-not-painted) with our state within RENDER_LAG_MAX_S of OUR
  // last change, before we change again. Needs look-ahead (core's next dot), so it is a post-pass over the finished samples.
  if (host === 'desktop') {
    for (const [key, r] of Object.entries(roots)) {
      r.samples.forEach((sm, i) => {
        if (sm.parity !== 'MISMATCH') return;
        const nextChange = r.samples.slice(i + 1).find(o => o.since !== sm.since)?.since ?? Infinity;
        const hit = (desk.dots[key] ?? []).find(d => d.t >= sm.t && classifyParity(sm.state, d.label) !== 'MISMATCH');
        const convergedAt = hit && hit.t <= nextChange ? hit.t : null;
        const parity = classifyParity(sm.state, sm.core, { since: sm.since, convergedAt });
        if (parity === 'allowed:render-lag' && convergedAt !== null) { sm.parity = parity; sm.lag_s = Math.round((convergedAt - sm.since) * 1000) / 1000; }
      });
    }
  }

  return { v: 1, name: String(head.name ?? ''), host, step_s: stepS, skipped, roots };
}

export function replayJson(traceLines: readonly (string | object)[], opts: ReplayOptions = {}): string {
  return canonicalJson(replay(traceLines, opts));
}
