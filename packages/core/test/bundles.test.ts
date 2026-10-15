import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import fc from 'fast-check';
import { buildAll, HEADER } from '../build.mjs';
import { replayJson as sourceReplayJson } from '../index.ts';

const repoFile = (rel: string) => new URL(`../../../${rel}`, import.meta.url);
const DESKTOP = 'desktop/core.bundle.js';
const TUI = 'tui/core.bundle.mjs';

test('the committed bundles are exactly what build.mjs produces now (fresh), and carry the GENERATED header', async () => {
  const built = await buildAll();
  assert.deepEqual(built.map(b => b.rel).sort(), [DESKTOP, TUI]);
  for (const b of built) {
    assert.equal(readFileSync(repoFile(b.rel), 'utf8'), b.text, `${b.rel} is stale: run npm run build in packages/core`);
    assert.ok(b.text.startsWith(HEADER + '\n'));
  }
});

test('both bundles are self-contained and import-free (the desktop loader resolves only @hermes/plugin-sdk/react)', () => {
  for (const rel of [DESKTOP, TUI]) {
    const code = readFileSync(repoFile(rel), 'utf8');
    assert.ok(!/^\s*import\b/m.test(code), `${rel} has an import statement`);
    assert.ok(!/\bimport\s*\(/.test(code), `${rel} has a dynamic import`);
    assert.ok(!/\brequire\s*\(/.test(code), `${rel} calls require`);
    assert.ok(!/\bfrom\s*["']node:/.test(code), `${rel} imports a node builtin`);
  }
});

test('the build is deterministic: no timestamps, no absolute paths', async () => {
  const [a, b] = [await buildAll(), await buildAll()];
  assert.deepEqual(a, b);
  for (const x of a) assert.ok(!x.text.includes('/home/') && !x.text.includes(process.cwd()), `${x.rel} leaks a path`);
});

const bundles = async () => ({
  desktop: await import(repoFile(DESKTOP).href),
  tui: await import(repoFile(TUI).href),
});

test('both bundles export the same API as index.ts, including the reducers and the replayer', async () => {
  const { desktop, tui } = await bundles();
  const idx = await import('../index.ts');
  assert.deepEqual(Object.keys(desktop).sort(), Object.keys(idx).sort());
  assert.deepEqual(Object.keys(tui).sort(), Object.keys(idx).sort());
  for (const name of ['replay', 'replayJson', 'hookReduce', 'hookResolve', 'desktopReduce', 'desktopResolve', 'classifyParity', 'allocate', 'renderModel']) assert.equal(typeof desktop[name], 'function', name);
});

// ---- property: random traces replay identically through source, desktop bundle and tui bundle -------------------------

const FC = { seed: 2909, numRuns: 1000 };
const HOOKS = ['on_session_reset', 'on_session_start', 'pre_llm_call', 'post_llm_call', 'on_session_end', 'on_session_finalize', 'pre_tool_call', 'post_tool_call',
  'pre_approval_request', 'post_approval_response', 'api_request_error', 'pre_verify', 'heartbeat', 'pid_dead', 'binding', 'on_stream_delta'];

const hookTrace = fc.record({
  gaps: fc.array(fc.tuple(fc.constantFrom(0, 0, 0.1, 0.6, 1, 5, 19.9, 21), fc.constantFrom('r1', 'r2', 'r3', 'r4'), fc.constantFrom(...HOOKS), fc.constantFrom('A', 'B'),
    fc.constantFrom('clarify', 'terminal'), fc.constantFrom('c1', 'c2', 'a1'), fc.boolean()), { minLength: 1, maxLength: 40 }),
  step: fc.constantFrom(0.25, 0.5, 1, 3),
}).map(({ gaps, step }) => {
  let t = 0;
  const rows: object[] = [{ v: 1, src: 'meta', kind: 'trace', name: 'prop', host: 'tui' }];
  for (const [dt, root, kind, profile, tool, id, flag] of gaps) {
    t += dt;
    rows.push({ v: 1, t, src: kind === 'heartbeat' || kind === 'pid_dead' ? 'liveness' : 'hook', profile, session: `${root}-s`, lineage_root: root, kind, payload: { tool_name: tool, tool_call_id: id, completed: flag, bound: flag } });
  }
  return { rows, step };
});

const deskTrace = fc.record({
  gaps: fc.array(fc.tuple(fc.constantFrom(0, 0.3, 1, 7, 30), fc.constantFrom('state', 'session.info', 'message.start', 'message.complete', 'dot'), fc.constantFrom('rt1', 'rt2'),
    fc.constantFrom('open', 'closed', 'connecting'), fc.boolean(), fc.constantFrom('Session running', 'Needs your input', '', 'Background task running'), fc.constantFrom('error', 'complete')), { minLength: 1, maxLength: 40 }),
  step: fc.constantFrom(0.5, 1, 2),
}).map(({ gaps, step }) => {
  let t = 0;
  const rows: object[] = [{ v: 1, src: 'meta', kind: 'trace', name: 'prop-d', host: 'desktop' }];
  for (const [dt, kind, rt, gateway, busy, label, status] of gaps) {
    t += dt;
    const stored = `st-${rt}`;
    rows.push(kind === 'dot'
      ? { v: 1, t, src: 'desktop.dot', profile: 'A', session: stored, lineage_root: null, kind, payload: { label } }
      : { v: 1, t, src: kind === 'state' ? 'desktop.state' : 'desktop.event', profile: 'A', session: kind === 'state' ? null : rt, lineage_root: null, kind,
          payload: kind === 'state' ? { gateway, busyBySession: { [rt]: busy } } : kind === 'session.info' ? { stored_session_id: stored } : { status } });
  }
  return { rows, step };
});

test('property (1000 runs): random hook traces give byte-identical replay output from source, desktop bundle and tui bundle', async () => {
  const { desktop, tui } = await bundles();
  fc.assert(fc.property(hookTrace, ({ rows, step }) => {
    const want = sourceReplayJson(rows, { stepS: step });
    assert.equal(desktop.replayJson(rows, { stepS: step }), want);
    assert.equal(tui.replayJson(rows, { stepS: step }), want);
  }), FC);
});

test('property (1000 runs): random desktop traces give byte-identical replay output from source, desktop bundle and tui bundle', async () => {
  const { desktop, tui } = await bundles();
  fc.assert(fc.property(deskTrace, ({ rows, step }) => {
    const want = sourceReplayJson(rows, { stepS: step });
    assert.equal(desktop.replayJson(rows, { stepS: step }), want);
    assert.equal(tui.replayJson(rows, { stepS: step }), want);
  }), FC);
});
