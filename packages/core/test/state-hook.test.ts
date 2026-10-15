import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initial, reduce, resolve, trackInit, trackStep, STALE_S, REVIEW_DWELL_S, type HookEvent, type HookModel } from '../domain/state-hook.ts';

const ev = (t: number, kind: string, payload: HookEvent['payload'] = {}): HookEvent => ({ t, kind, payload });
const fold = (events: HookEvent[], m: HookModel = initial()): HookModel => events.reduce(reduce, m);
const stateAfter = (events: HookEvent[], now?: number) => resolve(fold(events), now ?? events[events.length - 1].t);

// ---- contract §2 table: one test per row (event -> resolved state) -------------------------------------

test('on_session_reset: a fresh window is idle, and it wipes turn, pending approvals, fault and review state', () => {
  const dirty = [ev(0, 'pre_llm_call'), ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }), ev(2, 'api_request_error'), ev(3, 'pre_verify')];
  assert.equal(stateAfter(dirty), 'needs-you');
  assert.equal(stateAfter([...dirty, ev(4, 'on_session_reset')]), 'idle');
  assert.equal(stateAfter([...dirty, ev(4, 'on_session_reset')], 4.1), 'idle');   // review_until is gone too
});

test('on_session_start: no state effect (it only fires late, at the first turn)', () => {
  assert.equal(stateAfter([ev(0, 'on_session_reset'), ev(1, 'on_session_start')]), 'idle');
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'on_session_start')]), 'working');
  assert.equal(stateAfter([ev(0, 'api_request_error'), ev(1, 'on_session_start')]), 'fault');
});

test('pre_llm_call: working, and a new turn clears the sticky fault and finalized', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call')]), 'working');
  assert.equal(stateAfter([ev(0, 'api_request_error'), ev(1, 'pre_llm_call')]), 'working');
  assert.equal(resolve(fold([ev(0, 'on_session_finalize'), ev(1, 'pre_llm_call')]), 1), 'working');
});

test('post_llm_call: clears fault but the turn is still open (on_session_end closes it)', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'api_request_error'), ev(2, 'post_llm_call')]), 'working');
  assert.equal(stateAfter([ev(0, 'api_request_error'), ev(1, 'post_llm_call')]), 'idle');
});

test('on_session_end{completed:true}: turn over, idle, fault cleared', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'on_session_end', { completed: true })]), 'idle');
  assert.equal(stateAfter([ev(0, 'api_request_error'), ev(1, 'on_session_end', { completed: true })]), 'idle');
});

test('on_session_end{completed:false}: turn over and pending cleared, but a fault is NOT cleared', () => {
  const m = [ev(0, 'pre_llm_call'), ev(1, 'pre_approval_request', { tool_call_id: 'a1' }), ev(2, 'api_request_error'), ev(3, 'on_session_end', { completed: false, interrupted: true })];
  assert.equal(stateAfter(m), 'fault');
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'on_session_end', { completed: false })]), 'idle');
});

test('on_session_finalize: the session is over, unknown (never the last known state)', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'on_session_finalize')]), 'unknown');
  assert.equal(stateAfter([ev(0, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }), ev(1, 'on_session_finalize')]), 'unknown');
});

test('pre_tool_call / post_tool_call on clarify: needs-you from ask until the matching post', () => {
  const ask = [ev(0, 'pre_llm_call'), ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' })];
  assert.equal(stateAfter(ask), 'needs-you');
  assert.equal(stateAfter([...ask, ev(2, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' })]), 'working');
});

test('other tools never raise needs-you', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'pre_tool_call', { tool_name: 'terminal', tool_call_id: 'c1' })]), 'working');
});

test('pre_approval_request / post_approval_response: needs-you keyed on tool_call_id', () => {
  const open = [ev(0, 'pre_llm_call'), ev(1, 'pre_approval_request', { tool_call_id: 'a1', session_key: 'k', pattern_key: 'p' })];
  assert.equal(stateAfter(open), 'needs-you');
  assert.equal(stateAfter([...open, ev(2, 'post_approval_response', { tool_call_id: 'a1', choice: 'deny' })]), 'working');
});

test('approval without a tool_call_id is keyed on session_key/pattern_key', () => {
  const open = [ev(0, 'pre_llm_call'), ev(1, 'pre_approval_request', { session_key: 'k', pattern_key: 'rm' })];
  assert.equal(stateAfter(open), 'needs-you');
  assert.equal(stateAfter([...open, ev(2, 'post_approval_response', { session_key: 'other', pattern_key: 'rm' })]), 'needs-you');   // a different key does not clear it
  assert.equal(stateAfter([...open, ev(2, 'post_approval_response', { session_key: 'k', pattern_key: 'rm' })]), 'working');
});

test('api_request_error: fault, sticky across heartbeats with no turn-end hook (HTTP 401)', () => {
  const evs = [ev(0, 'pre_llm_call'), ev(1, 'api_request_error', { status_code: 401, retryable: false })];
  // working turn is still open, but fault outranks working
  assert.equal(stateAfter(evs), 'fault');
  const hb = Array.from({ length: 12 }, (_, i) => ev(5 * (i + 1), 'heartbeat'));
  assert.equal(resolve(fold([...evs, ...hb]), 60), 'fault');
  assert.equal(stateAfter([...evs, ev(70, 'pre_llm_call')]), 'working');   // cleared by the next turn
});

test('pre_verify: review for the 0.6 s minimum dwell, then idle', () => {
  assert.equal(REVIEW_DWELL_S, 0.6);
  const m = fold([ev(10, 'pre_llm_call'), ev(20, 'pre_verify'), ev(20.1, 'on_session_end', { completed: true })]);
  assert.equal(resolve(m, 20.1), 'review');
  assert.equal(resolve(m, 20.59), 'review');
  assert.equal(resolve(m, 20.6), 'idle');   // now < review_until is strict
});

test('pre_verify while the turn is open stays working (review is below working)', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'pre_verify')], 1.1), 'working');
});

test('heartbeat keeps the session alive and revives pid_dead', () => {
  const m = fold([ev(0, 'pre_llm_call'), ev(5, 'heartbeat'), ev(10, 'heartbeat')]);
  assert.equal(resolve(m, 29.9), 'working');
});

test('pid_dead is unknown, hooks do NOT revive it, a heartbeat does, and so does on_session_reset', () => {
  const dead = [ev(0, 'pre_llm_call'), ev(1, 'pid_dead')];
  assert.equal(stateAfter(dead), 'unknown');
  assert.equal(stateAfter([...dead, ev(2, 'pre_llm_call')]), 'unknown');
  assert.equal(stateAfter([...dead, ev(2, 'on_session_end', { completed: true })]), 'unknown');
  assert.equal(stateAfter([...dead, ev(3, 'heartbeat')]), 'working');
  assert.equal(stateAfter([...dead, ev(3, 'on_session_reset')]), 'idle');
});

test('binding{bound:false} is unknown, binding{bound:true} restores', () => {
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'binding', { bound: false })]), 'unknown');
  assert.equal(stateAfter([ev(0, 'pre_llm_call'), ev(1, 'binding', { bound: false }), ev(2, 'binding', { bound: true })]), 'working');
});

// ---- resolve: staleness, precedence ------------------------------------------------------------------

test('a model that has seen nothing resolves to unknown', () => {
  assert.equal(resolve(initial(), 0), 'unknown');
});

test('stale is unknown, never the last known state: working goes unknown strictly after 20 s of silence', () => {
  assert.equal(STALE_S, 20);
  const m = fold([ev(100, 'pre_llm_call')]);
  assert.equal(resolve(m, 120), 'working');
  assert.equal(resolve(m, 120.001), 'unknown');
  const needs = fold([ev(100, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' })]);
  assert.equal(resolve(needs, 121), 'unknown');   // even needs-you does not outlive a dead owner
});

test('precedence: unknown > needs-you > fault > working > review > idle', () => {
  const base = [ev(0, 'pre_llm_call'), ev(1, 'pre_verify'), ev(1, 'api_request_error')];
  assert.equal(resolve(fold(base), 1.1), 'fault');                          // fault > working > review
  const pend = [...base, ev(1.05, 'pre_approval_request', { tool_call_id: 'a' })];
  assert.equal(resolve(fold(pend), 1.1), 'needs-you');                      // needs-you > fault
  assert.equal(resolve(fold([...pend, ev(1.06, 'binding', { bound: false })]), 1.1), 'unknown');   // unknown > needs-you
  assert.equal(resolve(fold([ev(0, 'pre_llm_call'), ev(1, 'pre_verify')]), 1.1), 'working');       // working > review
  assert.equal(resolve(fold([ev(0, 'pre_llm_call'), ev(1, 'pre_verify'), ev(1.01, 'on_session_end', { completed: true })]), 1.1), 'review');
});

// ---- clarify cancel-and-re-ask ---------------------------------------------------------------------------

test('clarify cancelled then re-asked is keyed on tool_call_id: the old post cannot clear the new ask, the new post does', () => {
  const asks = [
    ev(0, 'pre_llm_call'),
    ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }),
    ev(2, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }),   // Ctrl-C cancel
    ev(3, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c2' }),    // model re-asks
  ];
  assert.equal(stateAfter(asks), 'needs-you');
  assert.equal(stateAfter([...asks, ev(4, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' })]), 'needs-you');   // late duplicate of the OLD id
  assert.equal(stateAfter([...asks, ev(4, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c2' })]), 'working');
  // overlap: the re-ask is observed before the cancel's post
  const overlap = [ev(0, 'pre_llm_call'), ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }), ev(2, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c2' }), ev(3, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' })];
  assert.equal(stateAfter(overlap), 'needs-you');
});

test('a turn end drops every pending ask (a stuck needs-you cannot outlive its turn)', () => {
  const evs = [ev(0, 'pre_llm_call'), ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }), ev(2, 'on_session_end', { completed: false, interrupted: true })];
  assert.equal(stateAfter(evs), 'idle');
});

// ---- since tracker, purity -----------------------------------------------------------------------------

test('since is the time of the last change of the RESOLVED state, not of the last event', () => {
  let m = initial();
  let tr = trackInit();
  const seen: Array<[number, string, number]> = [];
  const step = (t: number, e?: HookEvent) => {
    if (e) m = reduce(m, e);
    tr = trackStep(tr, resolve(m, t), t);
    seen.push([t, tr.state, tr.since]);
  };
  step(0, ev(0, 'on_session_reset'));
  step(1, ev(1, 'pre_llm_call'));
  step(2, ev(2, 'post_llm_call'));       // still working: since stays 1
  step(10);
  step(21.5);                            // 19.5 s of silence: still working
  step(22.5);                            // 20.5 s of silence: stale -> unknown, observed at the tick
  step(23);
  assert.deepEqual(seen, [[0, 'idle', 0], [1, 'working', 1], [2, 'working', 1], [10, 'working', 1], [21.5, 'working', 1], [22.5, 'unknown', 22.5], [23, 'unknown', 22.5]]);
});

test('reduce and resolve are pure: the input model is never mutated', () => {
  const m0 = initial();
  const snap = JSON.stringify(m0);
  const m1 = reduce(m0, ev(1, 'pre_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }));
  resolve(m1, 2);
  assert.equal(JSON.stringify(m0), snap);
  assert.notEqual(m1, m0);
  const snap1 = JSON.stringify(m1);
  reduce(m1, ev(2, 'post_tool_call', { tool_name: 'clarify', tool_call_id: 'c1' }));
  assert.equal(JSON.stringify(m1), snap1);
});

test('unrecognised hooks still count as proof of life (every event sets last_seen) but change nothing else', () => {
  const m = fold([ev(0, 'pre_llm_call'), ev(15, 'on_stream_delta'), ev(30, 'something_new')]);
  assert.equal(resolve(m, 45), 'working');
});
