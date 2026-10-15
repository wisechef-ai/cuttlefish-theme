#!/usr/bin/env node
// Cross-bundle parity runner. Replays every tools/traces/*.jsonl through BOTH committed bundles
// (desktop/core.bundle.js and tui/core.bundle.mjs) and requires byte-identical canonical output.
//
//   node tools/traces/parity.mjs [--require-all] [--dir <traces dir>] [--desktop-bundle <f>] [--tui-bundle <f>]
//
// Writes tools/traces/out/<name>.<bundle>.json (gitignored). Prints per-trace states reached, a
// reachability table and, for desktop traces, the core-dot parity counts.
// Exit: 0 ok | 1 bundles differ or a trace is unreadable | 2 --require-all and a state is never reached
//       | 3 a desktop sample is a MISMATCH against core's dot.   (1 wins over 3 wins over 2.)
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const STATES = ['idle', 'working', 'review', 'needs-you', 'fault', 'unknown'];

const args = process.argv.slice(2);
const flag = n => args.includes(n);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const dir = resolve(opt('--dir', here));
const bundlePaths = { desktop: resolve(opt('--desktop-bundle', join(root, 'desktop/core.bundle.js'))), tui: resolve(opt('--tui-bundle', join(root, 'tui/core.bundle.mjs'))) };
const bundles = {};
for (const [k, p] of Object.entries(bundlePaths)) bundles[k] = await import(pathToFileURL(p).href);

const files = readdirSync(dir).filter(f => f.endsWith('.jsonl')).sort();
const outDir = join(dir, 'out');
let diffs = 0, bad = 0, mismatches = 0;
const lags = {};   // trace -> distinct render-lag episodes (one per root + our-change time), seconds
const reached = Object.fromEntries(STATES.map(s => [s, []]));
const rows = [];
const parity = {};

for (const f of files) {
  const name = f.replace(/\.jsonl$/, '');
  const lines = readFileSync(join(dir, f), 'utf8').split('\n').filter(l => l.trim() !== '');
  const outs = {};
  try {
    for (const [k, b] of Object.entries(bundles)) outs[k] = b.replayJson(lines);
  } catch (e) {
    bad++;
    console.log(`ERROR ${name}: ${e.message}`);
    continue;
  }
  mkdirSync(outDir, { recursive: true });
  for (const [k, text] of Object.entries(outs)) writeFileSync(join(outDir, `${name}.${k}.json`), text + '\n');
  if (outs.desktop !== outs.tui) { diffs++; console.log(`DIFF ${name}: desktop bundle and tui bundle disagree (see out/${name}.desktop.json vs out/${name}.tui.json)`); }
  const r = JSON.parse(outs.tui);
  const seen = new Set();
  for (const root_ of Object.values(r.roots)) for (const s of root_.samples) {
    seen.add(s.state);
    if (s.parity === 'allowed:render-lag') (lags[name] ??= new Map()).set(`${Object.keys(r.roots).find(k => r.roots[k] === root_)}@${s.since}`, s.lag_s);
    if (s.parity) parity[name] = { ...(parity[name] ?? {}), [s.parity]: ((parity[name] ?? {})[s.parity] ?? 0) + 1 };
  }
  if (r.host === 'desktop') parity[name] = { match: 0, MISMATCH: 0, ...(parity[name] ?? {}) };
  for (const s of STATES) if (seen.has(s)) reached[s].push(name);
  rows.push([name, r.host, String(Object.keys(r.roots).length), STATES.filter(s => seen.has(s)).join(' ')]);
}

if (files.length === 0) console.log(`no *.jsonl traces in ${dir}`);
const w = rows.reduce((m, r) => Math.max(m, r[0].length), 5);
console.log(`${'trace'.padEnd(w)}  ${'host'.padEnd(7)}  roots  states reached`);
for (const [n, h, c, s] of rows) console.log(`${n.padEnd(w)}  ${h.padEnd(7)}  ${c.padEnd(5)}  ${s}`);
console.log('\nreachability (state -> traces that reach it)');
for (const s of STATES) console.log(`${s.padEnd(10)}  ${reached[s].length ? reached[s].join(', ') : '-'}`);
for (const [n, c] of Object.entries(parity)) {
  mismatches += c.MISMATCH ?? 0;
  console.log(`\ncore-dot parity ${n}: ${Object.keys(c).sort().map(k => `${k}=${c[k]}`).join(' ')}`);
}
const med = a => { const b = [...a].sort((x, y) => x - y), n = b.length; return n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2; };
const allLags = [];
for (const [n, m] of Object.entries(lags)) { const v = [...m.values()]; allLags.push(...v); console.log(`render-lag ${n}: episodes=${v.length} max=${Math.max(...v) * 1000} ms median=${Math.round(med(v) * 1e6) / 1000} ms`); }
if (allLags.length) console.log(`render-lag all desktop traces: episodes=${allLags.length} max=${Math.max(...allLags) * 1000} ms median=${Math.round(med(allLags) * 1e6) / 1000} ms (limit 500 ms)`);
const missing = STATES.filter(s => reached[s].length === 0);
if (flag('--require-all') && missing.length) console.log(`\nNOT REACHED: ${missing.join(', ')}`);

const code = diffs || bad ? 1 : mismatches ? 3 : flag('--require-all') && missing.length ? 2 : 0;
console.log(`\nexit ${code}`);
process.exit(code);
