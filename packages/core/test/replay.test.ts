import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { replay, replayJson, canonicalJson, type ReplayResult, type ReplaySample } from '../app/replay.ts';
import { allocate, SLOTS } from '../domain/identity.ts';

const lines = (name: string): string[] => readFileSync(new URL(`./fixtures/${name}.jsonl`, import.meta.url), 'utf8').split('\n').filter(l => l.trim() !== '');
const header = (host: string, name = 't') => ({ v: 1, src: 'meta', kind: 'trace', name, host, profiles: ['A'] });
const hook = (t: number, root: string, kind: string, payload: object = {}, profile = 'A', session = root) => ({ v: 1, t, src: 'hook', profile, session, lineage_root: root, kind, payload });
const sampleAt = (r: ReplayResult, root: string, t: number, on: 'event' | 'tick'): ReplaySample => {
  const s = r.roots[root].samples.find(x => x.t === t && x.on === on);
  assert.ok(s, `no ${on} sample at t=${t} for ${root}`);
  return s;
};

// ---- canonical JSON -----------------------------------------------------------------------------------------

test('canonicalJson sorts object keys at every depth and keeps array order', () => {
  assert.equal(canonicalJson({ b: 1, a: { d: [3, 1], c: null } }), '{"a":{"c":null,"d":[3,1]},"b":1}');
});

// ---- hook trace: every state reached, observed at events AND ticks ---------------------------------------------------

test('a TUI trace is replayed to the resolved state at every event and at every tick', () => {
  const r = replay(lines('tui-turn'));
  assert.equal(r.host, 'tui');
  assert.equal(r.name, 'tui-turn');
  const at = (t: number, on: 'event' | 'tick') => sampleAt(r, 'R1', t, on).state;
  assert.equal(at(0, 'event'), 'idle');
  assert.equal(at(3, 'tick'), 'working');
  assert.equal(at(5, 'tick'), 'needs-you');             // clarify c1 open 4 -> 6
  assert.equal(at(6, 'event'), 'working');
  assert.equal(at(7.1, 'event'), 'review');             // pre_verify 7, turn ends 7.1: dwell holds review
  assert.equal(at(8, 'tick'), 'idle');                  // sampled before the pre_llm_call at 8: dwell over
  assert.equal(at(8, 'event'), 'working');
  assert.equal(at(9, 'event'), 'fault');
  assert.equal(at(29, 'tick'), 'fault');                // 20.0 s of silence is not yet stale
  assert.equal(at(30, 'tick'), 'unknown');              // stale -> unknown observed at a synthetic tick, no event needed
});

test('every one of the six states is reachable from the turn trace', () => {
  const r = replay(lines('tui-turn'));
  assert.deepEqual([...new Set(r.roots.R1.samples.map(s => s.state))].sort(), ['fault', 'idle', 'needs-you', 'review', 'unknown', 'working']);
});

test('since is the time of the last change of the resolved state', () => {
  const r = replay(lines('tui-turn'));
  assert.equal(sampleAt(r, 'R1', 3, 'tick').since, 2);
  assert.equal(sampleAt(r, 'R1', 29, 'tick').since, 9);
  assert.equal(sampleAt(r, 'R1', 30, 'tick').since, 30);
  assert.equal(sampleAt(r, 'R1', 31, 'tick').since, 30);
});

test('stepS controls tick density: 0.5 s ticks observe the review dwell, 1 s ticks cannot', () => {
  const half = replay(lines('tui-turn'), { stepS: 0.5 });
  assert.equal(sampleAt(half, 'R1', 7.5, 'tick').state, 'review');
  assert.equal(sampleAt(half, 'R1', 8, 'tick').state, 'idle');
  const one = replay(lines('tui-turn'), { stepS: 1 });
  assert.equal(one.roots.R1.samples.filter(s => s.on === 'tick' && s.state === 'review').length, 0);
});

test('the replay runs past the last event so the final stale -> unknown is observed', () => {
  const r = replay([header('tui'), hook(0, 'R', 'pre_llm_call')]);
  const last = r.roots.R.samples[r.roots.R.samples.length - 1];
  assert.equal(last.state, 'unknown');
});

test('samples are time-ordered and events at the same instant are applied together before one sample', () => {
  const r = replay([header('tui'), hook(1, 'R', 'pre_llm_call'), hook(1, 'R', 'pre_verify'), hook(1, 'R', 'on_session_end', { completed: true })]);
  const ev = r.roots.R.samples.filter(s => s.on === 'event');
  assert.equal(ev.length, 1);
  assert.equal(ev[0].state, 'review');
  const ts = r.roots.R.samples.map(s => s.t);
  assert.deepEqual(ts, [...ts].sort((a, b) => a - b));
});

test('unsorted input is replayed in time order', () => {
  const a = replay([header('tui'), hook(2, 'R', 'on_session_end', { completed: true }), hook(1, 'R', 'pre_llm_call')]);
  const b = replay([header('tui'), hook(1, 'R', 'pre_llm_call'), hook(2, 'R', 'on_session_end', { completed: true })]);
  assert.equal(canonicalJson(a), canonicalJson(b));
  assert.equal(sampleAt(a, 'R', 1, 'event').state, 'working');
});

test('liveness lines drive pid_dead and heartbeat; a dead pid is unknown until a heartbeat', () => {
  const live = (t: number, kind: string) => ({ v: 1, t, src: 'liveness', profile: 'A', session: 'R', lineage_root: 'R', kind, payload: {} });
  const r = replay([header('tui'), hook(0, 'R', 'pre_llm_call'), live(2, 'pid_dead'), hook(3, 'R', 'pre_llm_call'), live(4, 'heartbeat')]);
  assert.equal(sampleAt(r, 'R', 2, 'event').state, 'unknown');
  assert.equal(sampleAt(r, 'R', 3, 'event').state, 'unknown');
  assert.equal(sampleAt(r, 'R', 4, 'event').state, 'working');
});

test('lines with no lineage root and no session are skipped and counted, never guessed', () => {
  const r = replay([header('tui'), { v: 1, t: 1, src: 'hook', profile: 'A', session: null, lineage_root: null, kind: 'pre_llm_call', payload: {} }, hook(2, 'R', 'pre_llm_call')]);
  assert.equal(r.skipped, 1);
  assert.deepEqual(Object.keys(r.roots), ['R']);
});

test('a trace without its header line is rejected', () => {
  assert.throws(() => replay([hook(1, 'R', 'pre_llm_call')]), /header/);
  assert.throws(() => replay([]), /header/);
});

// ---- identity during replay ----------------------------------------------------------------------------------------

test('rotation keeps the lineage root and its slot: every session id under one root is ONE entry with one identity', () => {
  const r = replay(lines('tui-rotation'));
  assert.deepEqual(Object.keys(r.roots).sort(), ['R1', 'R2']);       // S1, S2, S3 are all R1
  const r1 = r.roots.R1.identity!;
  const r2 = r.roots.R2.identity!;
  assert.equal(r1.slot, allocate('R1', []).slot);                    // first seen: no peers
  assert.equal(r2.slot, allocate('R2', [r1.slot]).slot);            // R2 saw R1's slot as a peer
  assert.notEqual(r1.slot, r2.slot);
  assert.equal(sampleAt(r, 'R1', 6, 'event').state, 'needs-you');   // state continued across the id change
  assert.equal(sampleAt(r, 'R1', 8, 'event').state, 'idle');
});

test('a later arrival never moves an existing root off its slot', () => {
  const few = replay([header('tui'), hook(0, 'R1', 'pre_llm_call')]);
  const many = replay([header('tui'), hook(0, 'R1', 'pre_llm_call'), ...Array.from({ length: 10 }, (_, i) => hook(1 + i, `X${i}`, 'pre_llm_call'))]);
  assert.deepEqual(many.roots.R1.identity, few.roots.R1.identity);
});

test('identity is per profile in first-seen order: another profile does not count as a peer', () => {
  const r = replay(lines('tui-two-profiles'));
  const a = ['RA1', 'RA2', 'RA3'].map(k => r.roots[k].identity!);
  assert.equal(a[0].slot, allocate('RA1', []).slot);
  assert.equal(a[1].slot, allocate('RA2', [a[0].slot]).slot);
  assert.equal(a[2].slot, allocate('RA3', [a[0].slot, a[1].slot]).slot);
  assert.equal(r.roots.RB1.identity!.slot, allocate('RB1', []).slot);   // B saw no peers although A held three slots
  assert.equal(r.roots.RB1.profile, 'B');
});

test('twenty sessions of one profile get twenty distinct slots; the 21st is crowded, never hidden', () => {
  const roots = Array.from({ length: SLOTS + 1 }, (_, i) => `lineage-${i}`);
  const r = replay([header('tui'), ...roots.map((k, i) => hook(i, k, 'pre_llm_call'))]);
  const first20 = roots.slice(0, SLOTS).map(k => r.roots[k].identity!);
  assert.equal(new Set(first20.map(i => i.slot)).size, SLOTS);
  assert.ok(first20.every(i => !i.crowded));
  assert.equal(r.roots[roots[SLOTS]].identity!.crowded, true);
});

test('identity hue is reported rounded to two decimals', () => {
  const r = replay([header('tui'), hook(0, 'R1', 'pre_llm_call')]);
  const h = r.roots.R1.identity!.hue_deg;
  assert.equal(h, Math.round(h * 100) / 100);
});

// ---- desktop trace -----------------------------------------------------------------------------------------------------

test('a desktop trace resolves per STORED id through runtime -> stored mapping, with core-dot parity per sample', () => {
  const r = replay(lines('desktop-basic'));
  assert.equal(r.host, 'desktop');
  assert.deepEqual(Object.keys(r.roots), ['st1']);
  const s = (t: number, on: 'event' | 'tick' = 'event') => sampleAt(r, 'st1', t, on);
  assert.equal(s(1).state, 'idle');
  assert.equal(s(1).parity, undefined);                              // no dot observed yet: nothing to compare
  assert.deepEqual([s(2).state, s(2).core, s(2).parity], ['working', 'Session running', 'match']);
  assert.deepEqual([s(4).state, s(4).parity], ['needs-you', 'match']);
  assert.deepEqual([s(6).state, s(6).parity], ['working', 'match']);
  assert.deepEqual([s(8).state, s(8).parity], ['fault', 'allowed:fault-not-painted']);   // error + dot clear land at one instant
  assert.deepEqual([s(10).state, s(10).parity], ['working', 'match']);
  assert.deepEqual([s(12).state, s(12).parity], ['unknown', 'allowed:gateway-not-open']);   // gateway closed, core still shows stale busy
  assert.deepEqual([s(16).state, s(16).parity], ['idle', 'match']);
  assert.equal(sampleAt(r, 'st1', 5, 'tick').state, 'needs-you');
  assert.equal(r.roots.st1.identity!.slot, allocate('st1', []).slot);
});

test('a desktop sample where our state and core disagree is reported MISMATCH', () => {
  const d = (t: number, src: string, kind: string, session: string | null, payload: object) => ({ v: 1, t, src, profile: 'A', session, lineage_root: null, kind, payload });
  const r = replay([header('desktop'), d(0, 'desktop.state', 'state', null, { gateway: 'open' }), d(1, 'desktop.event', 'session.info', 'rt', { stored_session_id: 'st' }),
    d(2, 'desktop.dot', 'dot', 'st', { label: 'Session running' })]);   // core says running, we have no busy signal
  assert.equal(sampleAt(r, 'st', 2, 'event').parity, 'MISMATCH');
});

// ---- determinism --------------------------------------------------------------------------------------------------------

test('two runs produce byte-identical canonical JSON', () => {
  for (const f of ['tui-turn', 'tui-rotation', 'tui-two-profiles', 'desktop-basic']) {
    assert.equal(replayJson(lines(f)), replayJson(lines(f)), f);
  }
});

test('lines may be given as strings or as parsed objects', () => {
  const raw = lines('tui-turn');
  assert.equal(replayJson(raw), replayJson(raw.map(l => JSON.parse(l))));
});
