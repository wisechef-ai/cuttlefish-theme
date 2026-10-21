import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initial, reduce, resolve, storedIds, classifyParity, CORE_DOT_LABELS, type DesktopInput, type DesktopModel } from '../domain/state-desktop.ts';

const info = (rt: string, stored: string): DesktopInput => ({ kind: 'session.info', session: rt, payload: { stored_session_id: stored } });
const snap = (gateway: string, busyBySession: Record<string, boolean> = {}): DesktopInput => ({ kind: 'state', payload: { gateway, busyBySession } });
const start = (rt: string): DesktopInput => ({ kind: 'message.start', session: rt });
const complete = (rt: string, status: string): DesktopInput => ({ kind: 'message.complete', session: rt, payload: { status } });
const dot = (stored: string, label: string): DesktopInput => ({ kind: 'dot', session: stored, payload: { label } });
const fold = (inputs: DesktopInput[], m: DesktopModel = initial()) => inputs.reduce(reduce, m);
const S = 'stored-1';

// ---- contract §3 table: one test per row -------------------------------------------------------------------

test('desktop.state snapshot: gateway open + busy[runtime] true is thinking, mapped runtime -> stored', () => {
  const m = fold([info('rt1', S), snap('open', { rt1: true })]);
  assert.equal(resolve(m, S), 'thinking');
  assert.equal(resolve(fold([snap('open', { rt1: false })], m), S), 'idle');
});

test('desktop.state snapshot: gateway not open is unknown, overriding a stale busy (upstream shows a killed session busy ~26 s)', () => {
  const busy = fold([info('rt1', S), snap('open', { rt1: true })]);
  for (const gw of ['closed', 'connecting']) assert.equal(resolve(fold([snap(gw, { rt1: true })], busy), S), 'unknown');
  assert.equal(resolve(fold([snap('open', { rt1: false })], fold([snap('closed', { rt1: true })], busy)), S), 'idle');   // reopened, busy cleared
});

test('before any snapshot the gateway is unknown, so everything is unknown', () => {
  assert.equal(resolve(fold([info('rt1', S)]), S), 'unknown');
  assert.equal(resolve(initial(), S), 'unknown');
});

test('message.complete with status error is fault, sticky until the next message.start', () => {
  const open = fold([snap('open'), info('rt1', S)]);
  const failed = fold([complete('rt1', 'error')], open);
  assert.equal(resolve(failed, S), 'fault');
  assert.equal(resolve(fold([snap('open', { rt1: false })], failed), S), 'fault');   // busy going false does not clear it
  assert.equal(resolve(fold([start('rt1')], failed), S), 'idle');
  assert.equal(resolve(fold([start('rt1'), snap('open', { rt1: true })], failed), S), 'thinking');
});

test('message.complete with any other status does not fault', () => {
  assert.equal(resolve(fold([snap('open'), info('rt1', S), complete('rt1', 'complete')]), S), 'idle');
});

test('desktop.dot "Needs your input" is needs-you (outranks fault and thinking); any other label clears it', () => {
  const base = fold([snap('open', { rt1: true }), info('rt1', S), complete('rt1', 'error')]);
  assert.equal(resolve(base, S), 'fault');
  const asked = fold([dot(S, 'Needs your input')], base);
  assert.equal(resolve(asked, S), 'needs-you');
  assert.equal(resolve(fold([dot(S, 'Session running')], asked), S), 'fault');
  assert.equal(resolve(fold([dot(S, '')], fold([start('rt1')], asked)), S), 'thinking');
});

test('needs-you also loses to a closed gateway', () => {
  assert.equal(resolve(fold([snap('closed'), info('rt1', S), dot(S, 'Needs your input')]), S), 'unknown');
});

test('desktop never resolves review (spike 07: no signal exists)', () => {
  const m = fold([snap('open', { rt1: true }), info('rt1', S), snap('open', { rt1: false })]);
  assert.notEqual(resolve(m, S), 'review');
});

// ---- runtime -> stored mapping with buffering ----------------------------------------------------------------

test('events for a runtime id with no mapping yet are buffered and applied once session.info maps it', () => {
  const early = fold([snap('open', { rt9: true }), start('rt9'), complete('rt9', 'error')]);
  assert.deepEqual(storedIds(early), []);                       // nothing is attributable yet
  const mapped = fold([info('rt9', 'stored-9')], early);
  assert.deepEqual(storedIds(mapped), ['stored-9']);
  assert.equal(resolve(mapped, 'stored-9'), 'fault');           // the buffered error landed on the stored id
});

test('buffered events keep their order: busy then a later idle snapshot ends idle, not busy', () => {
  const m = fold([snap('open', { rt9: true }), snap('open', { rt9: false }), info('rt9', 'stored-9')]);
  assert.equal(resolve(m, 'stored-9'), 'idle');
});

test('two runtime ids map to two stored ids independently', () => {
  const m = fold([snap('open', { a: true, b: false }), info('a', 'sa'), info('b', 'sb')]);
  assert.equal(resolve(m, 'sa'), 'thinking');
  assert.equal(resolve(m, 'sb'), 'idle');
  assert.deepEqual(storedIds(m), ['sa', 'sb']);
});

test('reduce is pure: the input model is never mutated', () => {
  const m0 = fold([snap('open'), info('rt1', S)]);
  const j = JSON.stringify(m0);
  reduce(m0, snap('open', { rt1: true }));
  reduce(m0, complete('rt1', 'error'));
  assert.equal(JSON.stringify(m0), j);
});

// ---- parity vs core's SessionStatusDot ----------------------------------------------------------------------------

test('core dot labels are the observed i18n strings', () => {
  assert.deepEqual(CORE_DOT_LABELS, { working: 'Session running', needsYou: 'Needs your input' });
});

test('parity: thinking / needs-you / idle must equal core; core idle dot has no label', () => {
  assert.equal(classifyParity('thinking', 'Session running'), 'match');
  assert.equal(classifyParity('needs-you', 'Needs your input'), 'match');
  assert.equal(classifyParity('idle', null), 'match');
  assert.equal(classifyParity('idle', ''), 'match');
});

test('parity: the only allowed divergences are unknown while the gateway is not open, and fault where core paints idle', () => {
  assert.equal(classifyParity('unknown', 'Session running'), 'allowed:gateway-not-open');
  assert.equal(classifyParity('unknown', null), 'allowed:gateway-not-open');
  assert.equal(classifyParity('fault', null), 'allowed:fault-not-painted');
  assert.equal(classifyParity('fault', ''), 'allowed:fault-not-painted');
});

test('parity: every other pairing is a MISMATCH', () => {
  assert.equal(classifyParity('thinking', null), 'MISMATCH');
  assert.equal(classifyParity('idle', 'Session running'), 'MISMATCH');
  assert.equal(classifyParity('needs-you', 'Session running'), 'MISMATCH');
  assert.equal(classifyParity('thinking', 'Needs your input'), 'MISMATCH');
  assert.equal(classifyParity('fault', 'Session running'), 'MISMATCH');
  assert.equal(classifyParity('idle', 'Background task running'), 'MISMATCH');
  assert.equal(classifyParity('review', null), 'MISMATCH');
});

// ---- P2-PARITY: busy is tracked per runtime id; the live focused pair maps early; render lag is bounded -------------

const focus = (gateway: string, busyBySession: Record<string, boolean>, rt: string, stored: string): DesktopInput =>
  ({ kind: 'state', payload: { gateway, busyBySession, focused_session_id: rt, focused_stored_session_id: stored } });

test('two runtimes -> one stored id: a stale idle runtime never masks the live busy one (desktop-kill t=43.5)', () => {
  // 'z-dead' sorts after 'a-live', so last-writer-wins would end idle
  const m = fold([info('z-dead', S), info('a-live', S), snap('open', { 'z-dead': false, 'a-live': true })]);
  assert.equal(resolve(m, S), 'thinking');
  assert.equal(resolve(fold([snap('open', { 'a-live': true, 'z-dead': false })], m), S), 'thinking');   // key order is irrelevant
  assert.equal(resolve(fold([snap('open', { 'z-dead': false, 'a-live': false })], m), S), 'idle');
});

test('a runtime absent from the latest snapshot no longer counts as busy', () => {
  const m = fold([info('a', S), info('b', S), snap('open', { a: true, b: true })]);
  assert.equal(resolve(m, S), 'thinking');
  assert.equal(resolve(fold([snap('open', { b: true })], m), S), 'thinking');
  assert.equal(resolve(fold([snap('open', {})], m), S), 'idle');
});

test('per-runtime busy line form: a later false of the SAME runtime clears it, another runtime does not', () => {
  const line = (rt: string, busy: boolean): DesktopInput => ({ kind: 'state', session: rt, payload: { gateway: 'open', busy } });
  const m = fold([info('a', S), info('b', S), line('a', true), line('b', false)]);
  assert.equal(resolve(m, S), 'thinking');
  assert.equal(resolve(fold([line('a', false)], m), S), 'idle');
});

test('the focused pair on a state snapshot maps runtime -> stored BEFORE any session.info', () => {
  const m = fold([focus('open', { rt1: true }, 'rt1', S)]);
  assert.deepEqual(storedIds(m), [S]);
  assert.equal(resolve(m, S), 'thinking');                       // no 3 s wait for session.info
});

test('a time-valid stored_session_id on a per-runtime state line maps too', () => {
  const m = fold([{ kind: 'state', session: 'rt1', payload: { gateway: 'open', busy: true, stored_session_id: S } }]);
  assert.equal(resolve(m, S), 'thinking');
});

test('parity render-lag: core repainting within 500 ms of our change is allowed, 600 ms is not, never converging is not', () => {
  assert.equal(classifyParity('thinking', '', { since: 10, convergedAt: 10.15 }), 'allowed:render-lag');
  assert.equal(classifyParity('thinking', '', { since: 10, convergedAt: 10.5 }), 'allowed:render-lag');
  assert.equal(classifyParity('thinking', '', { since: 10, convergedAt: 10.6 }), 'MISMATCH');
  assert.equal(classifyParity('thinking', '', { since: 10, convergedAt: null }), 'MISMATCH');
  assert.equal(classifyParity('idle', 'Session running', { since: 10, convergedAt: 10.2 }), 'allowed:render-lag');
  assert.equal(classifyParity('thinking', 'Session running', { since: 10, convergedAt: 99 }), 'match');   // agreement needs no lag
});

// ---- tool signal (CONTRACT §3, spike 07: tool.start/complete reach host.onEvent with the RUNTIME id) --------------------

const tstart = (rt: string, id: string, tool_name = 'terminal'): DesktopInput => ({ kind: 'tool.start', session: rt, payload: { tool_name, tool_call_id: id } });
const tdone = (rt: string, id: string, tool_name = 'terminal'): DesktopInput => ({ kind: 'tool.complete', session: rt, payload: { tool_name, tool_call_id: id } });

test('desktop tool signal: busy + an open tool is tool, tool.complete returns to thinking', () => {
  const busy = fold([info('rt1', S), snap('open', { rt1: true })]);
  assert.equal(resolve(fold([tstart('rt1', 'a')], busy), S), 'tool');
  assert.equal(resolve(fold([tstart('rt1', 'a'), tdone('rt1', 'a')], busy), S), 'thinking');
  assert.equal(resolve(fold([tstart('rt1', 'a'), tstart('rt1', 'b'), tdone('rt1', 'a')], busy), S), 'tool');   // parallel: until the last one
});

test('desktop tool signal: clarify is an ask not a tool; needs-you and fault outrank tool; idle never shows tool', () => {
  const busy = fold([info('rt1', S), snap('open', { rt1: true })]);
  assert.equal(resolve(fold([tstart('rt1', 'c', 'clarify')], busy), S), 'thinking');
  assert.equal(resolve(fold([tstart('rt1', 'a'), dot(S, 'Needs your input')], busy), S), 'needs-you');
  assert.equal(resolve(fold([tstart('rt1', 'a'), complete('rt1', 'error')], busy), S), 'fault');
  assert.equal(resolve(fold([tstart('rt1', 'a'), snap('open', { rt1: false })], busy), S), 'idle');   // tool never outlives busy
});

test('desktop tool signal: a turn boundary closes tools (a killed backend sends no tool.complete); only a busy mapped runtime counts', () => {
  const busy = fold([info('rt1', S), snap('open', { rt1: true }), tstart('rt1', 'a')]);
  assert.equal(resolve(fold([start('rt1')], busy), S), 'thinking');
  assert.equal(resolve(fold([complete('rt1', 'complete')], busy), S), 'thinking');
  const two = fold([info('rt1', S), info('rt2', S), snap('open', { rt1: false, rt2: true }), tstart('rt1', 'old')]);
  assert.equal(resolve(two, S), 'thinking');                      // the stale idle runtime's tool does not colour the live one
  assert.equal(resolve(fold([tstart('rt2', 'new')], two), S), 'tool');
});
