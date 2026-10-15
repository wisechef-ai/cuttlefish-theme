import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PARITY = new URL('../../../tools/traces/parity.mjs', import.meta.url).pathname;
const FIX = new URL('./fixtures/', import.meta.url).pathname;
const TUI_BUNDLE = new URL('../../../tui/core.bundle.mjs', import.meta.url).pathname;

function dirWith(...files: string[]): string {
  const d = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), 'parity-'));
  for (const f of files) copyFileSync(join(FIX, `${f}.jsonl`), join(d, `${f}.jsonl`));
  return d;
}
const run = (args: string[]) => spawnSync(process.execPath, [PARITY, ...args], { encoding: 'utf8' });

test('parity.mjs replays every trace through BOTH bundles, writes out/<name>.<bundle>.json, and exits 0 when they agree', () => {
  const d = dirWith('tui-turn', 'tui-rotation', 'desktop-basic');
  const r = run(['--dir', d]);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const out = readdirSync(join(d, 'out')).sort();
  assert.deepEqual(out, ['desktop-basic.desktop.json', 'desktop-basic.tui.json', 'tui-rotation.desktop.json', 'tui-rotation.tui.json', 'tui-turn.desktop.json', 'tui-turn.tui.json']);
  assert.equal(readFileSync(join(d, 'out/tui-turn.desktop.json'), 'utf8'), readFileSync(join(d, 'out/tui-turn.tui.json'), 'utf8'));
  assert.equal(JSON.parse(readFileSync(join(d, 'out/tui-turn.tui.json'), 'utf8')).roots.R1.samples.at(-1).state, 'unknown');
});

test('parity.mjs prints per-trace states reached and a reachability table', () => {
  const r = run(['--dir', dirWith('tui-turn', 'desktop-basic')]);
  assert.match(r.stdout, /tui-turn\s+tui\s+1\s+idle working review needs-you fault unknown/);
  assert.match(r.stdout, /desktop-basic\s+desktop\s+1\s+idle working needs-you fault unknown/);
  assert.match(r.stdout, /review\s+tui-turn\s*$/m);                 // only the tui trace reaches review
  assert.match(r.stdout, /idle\s+desktop-basic, tui-turn/);
});

test('--require-all exits 2 unless every one of the six states is reached by some trace', () => {
  const some = run(['--dir', dirWith('tui-rotation'), '--require-all']);
  assert.equal(some.status, 2, some.stdout);
  assert.match(some.stdout, /NOT REACHED: .*fault/);
  const all = run(['--dir', dirWith('tui-turn'), '--require-all']);
  assert.equal(all.status, 0, all.stdout + all.stderr);
});

test('desktop traces print core-dot parity counts; a MISMATCH exits 3', () => {
  const ok = run(['--dir', dirWith('desktop-basic')]);
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
  assert.match(ok.stdout, /match=\d+/);
  assert.match(ok.stdout, /allowed:gateway-not-open=\d+/);
  assert.match(ok.stdout, /allowed:fault-not-painted=\d+/);
  assert.match(ok.stdout, /MISMATCH=0/);
  const d = dirWith();
  const row = (o: object) => JSON.stringify({ v: 1, profile: 'A', lineage_root: null, ...o });
  writeFileSync(join(d, 'bad.jsonl'), [
    row({ src: 'meta', kind: 'trace', name: 'bad', host: 'desktop' }),
    row({ t: 0, src: 'desktop.state', session: null, kind: 'state', payload: { gateway: 'open' } }),
    row({ t: 1, src: 'desktop.event', session: 'rt', kind: 'session.info', payload: { stored_session_id: 'st' } }),
    row({ t: 2, src: 'desktop.dot', session: 'st', kind: 'dot', payload: { label: 'Session running' } }),   // core running, we are idle
  ].join('\n') + '\n');
  const bad = run(['--dir', d]);
  assert.equal(bad.status, 3, bad.stdout);
  assert.match(bad.stdout, /MISMATCH=[1-9]/);
});

test('when the two bundles disagree on a trace, parity.mjs exits 1 and names the trace', () => {
  const d = dirWith('tui-turn');
  const broken = join(d, 'broken-tui.mjs');
  // a deliberately wrong second bundle: same API, but the replayer lies about the first state
  writeFileSync(broken, readFileSync(TUI_BUNDLE, 'utf8').replace(/export\s*\{/, 'const __rj = replayJson; replayJson = (l, o) => __rj(l, o).replace("\\"idle\\"", "\\"fault\\""); export {'));
  const r = run(['--dir', d, '--tui-bundle', broken]);
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stdout + r.stderr, /DIFF.*tui-turn/);
});

test('an empty trace directory is not an error, but --require-all then exits 2', () => {
  const d = dirWith();
  assert.equal(run(['--dir', d]).status, 0);
  assert.equal(run(['--dir', d, '--require-all']).status, 2);
  assert.ok(!existsSync(join(d, 'out')) || readdirSync(join(d, 'out')).length === 0);
});
