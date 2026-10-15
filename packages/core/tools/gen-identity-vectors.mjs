#!/usr/bin/env node
// Generate fixtures/identity-vectors.json (>= 2,000 golden cases for contract §1).
//
// Two independent implementations must agree before a case is written:
//   * `preferred` is computed by Python hashlib.blake2b and compared with the TS port, and
//   * the whole allocation (slot, hue_deg, crowded) is recomputed by a Python reference
//     allocator written straight from the contract text, and compared with domain/identity.ts.
// Any mismatch exits 1 (fail loudly). P3's identity.py tests load the resulting file.
//
// usage: node tools/gen-identity-vectors.mjs [--check]   (--check: exit 1 if the committed file differs)
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { allocate, preferredSlot } from '../domain/identity.ts';

const OUT = new URL('../fixtures/identity-vectors.json', import.meta.url);

// ---- deterministic case construction (mulberry32; no Math.random) ----
let s = 2909 >>> 0;
const rnd = () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const int = n => Math.floor(rnd() * n);
const ALPHA = 'abcdefghijklmnopqrstuvwxyz0123456789_';
const WIDE = ['ł', 'ż', 'ü', 'é', '日', '本', '語', '한', 'ж', 'Ω', '🐙', '🌊'];
function root() {
  const kind = int(5);
  if (kind === 0) return `20260930_${String(100000 + int(899999))}_${Array.from({ length: 3 }, () => ALPHA[int(26)]).join('')}`; // hermes-style id
  if (kind === 1) return Array.from({ length: 1 + int(24) }, () => ALPHA[int(ALPHA.length)]).join('');
  if (kind === 2) return Array.from({ length: 1 + int(12) }, () => (rnd() < 0.5 ? WIDE[int(WIDE.length)] : ALPHA[int(26)])).join('');
  if (kind === 3) return ` ${Array.from({ length: 3 + int(8) }, () => ALPHA[int(26)]).join('')} `;      // inner spaces kept as-is
  return 'x'.repeat(1 + int(200));                                                                     // long
}
function peerSet(n) {
  const kind = int(3);
  if (n >= 20 && kind === 0) return Array.from({ length: n }, (_, i) => i % 20).sort(() => rnd() - 0.5);          // full occupancy (+ duplicates beyond 20)
  if (kind === 1) return Array.from({ length: n }, () => int(20));                                               // random, duplicates likely
  const pool = Array.from({ length: 20 }, (_, i) => i);                                                          // distinct
  for (let i = pool.length - 1; i > 0; i--) { const j = int(i + 1); [pool[i], pool[j]] = [pool[j], pool[i]]; }
  const distinct = pool.slice(0, Math.min(n, 20));
  while (distinct.length < n) distinct.push(distinct[int(distinct.length)]);                                    // pad with duplicates
  return distinct;
}
const cases = [];
for (let n = 0; n <= 25; n++) for (let i = 0; i < 80; i++) cases.push({ lineage_root: root(), peers: peerSet(n) });
for (let i = 0; i < 20; i++) cases.push({ lineage_root: root(), peers: Array.from({ length: 20 }, (_, k) => k) });   // exactly full
cases.push({ lineage_root: 'ledger', peers: [] });

// ---- Python: hashlib digests + an independent reference allocator ----
const PY = String.raw`
import hashlib, json, sys
ARC_START, SLOTS, CAP = 110.0, 20, 3
STEP = (340.0 - 110.0) / SLOTS
def preferred(r): return int.from_bytes(hashlib.blake2b(r.encode('utf-8'), digest_size=32).digest()[0:8], 'big') % SLOTS
def hue(k): return ARC_START + STEP * (k + 0.5)
def allocate(r, peers):
    pref = preferred(r)
    if not peers: return pref, hue(pref), False
    free = [k for k in range(SLOTS) if k not in peers]
    if not free: return pref, hue(pref), True
    score = lambda k: (min(CAP, min(abs(k - p) for p in peers)), -abs(k - pref), -k)
    k = max(free, key=score)
    return k, hue(k), min(abs(k - p) for p in peers) < 1
out = []
for c in json.load(sys.stdin):
    slot, h, crowded = allocate(c['lineage_root'], c['peers'])
    out.append({'preferred': preferred(c['lineage_root']), 'slot': slot, 'hue_deg': round(h, 2), 'crowded': crowded})
json.dump(out, sys.stdout)
`;
const r = spawnSync('python3', ['-c', PY], { input: JSON.stringify(cases), encoding: 'utf8', maxBuffer: 1 << 28 });
if (r.status !== 0) { console.error(r.stderr); process.exit(1); }
const py = JSON.parse(r.stdout);

let hashChecks = 0, fullChecks = 0;
const result = cases.map((c, i) => {
  const ts = allocate(c.lineage_root, c.peers);
  const tsPref = preferredSlot(c.lineage_root);
  if (tsPref !== py[i].preferred) { console.error(`PREFERRED MISMATCH ${JSON.stringify(c)} ts=${tsPref} py=${py[i].preferred}`); process.exit(1); }
  hashChecks++;
  if (ts.slot !== py[i].slot || Math.round(ts.hue_deg * 100) / 100 !== py[i].hue_deg || ts.crowded !== py[i].crowded) {
    console.error(`ALLOCATION MISMATCH ${JSON.stringify(c)} ts=${JSON.stringify(ts)} py=${JSON.stringify(py[i])}`); process.exit(1);
  }
  fullChecks++;
  return { lineage_root: c.lineage_root, peers: c.peers, slot: ts.slot, hue_deg: Math.round(ts.hue_deg * 100) / 100, crowded: ts.crowded, preferred: tsPref };
});

const text = JSON.stringify({ schema: 'cf2909.identity-vectors/1', contract: 'packages/core/CONTRACT.md §1',
  generator: 'tools/gen-identity-vectors.mjs (TS impl, cross-checked against python hashlib + a python reference allocator)', cases: result }) + '\n';
if (process.argv.includes('--check')) {
  if (readFileSync(OUT, 'utf8') !== text) { console.error('identity-vectors.json is stale: run node tools/gen-identity-vectors.mjs'); process.exit(1); }
  console.log('identity-vectors.json fresh');
} else {
  writeFileSync(OUT, text);
}
console.log(`identity vectors: ${result.length} cases; preferred cross-checked vs hashlib: ${hashChecks}; full allocation cross-checked vs python reference: ${fullChecks}`);
