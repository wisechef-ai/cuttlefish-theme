import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildManifest, uncovered, type ManifestInput, type Pixels } from './manifest.ts'

const px = (m: number): Pixels => ({ organs_detected: 30, p95_dL: 0.03, mean_dL: m, lowK: 0.1, highK: 0.7 })
const input = (over: Partial<ManifestInput> = {}): ManifestInput => ({
  commit: 'c', pluginSha: 'p', core: { version: 'v0.22.7', sha: 'b200f5bc60e', desktop_build: 'source' }, isolation: { gateway_port: 5 },
  video: { path: 'evidence/v2/capture.mp4', sha256: 'v', start_epoch: 1 },
  sessions: [{ stored_id: 's', expected: 'resting', dom_state: 'resting', dom_dump: 'dom/s.resting.json', title: 't' }], stills: [],
  windows: Object.fromEntries(['idle_on', 'idle_off', 'working_on', 'working_off'].map(n => [n, { file: `cpu/${n}.csv`, dom_dump: `dom/win.${n}.json`, roles: { '1': 'renderer' } }])),
  order: ['idle_on', 'idle_off', 'working_off', 'working_on'], rows: 8, timeline: [], files: [], capturedAt: 'now',
  measured: {
    pixels: { resting: px(0.01), working: px(0.02), needs_you: px(0.05), error: px(0.012) },
    cpu: { idle_on: { mean_pct: 2.004, window_s: 61 }, idle_off: { mean_pct: 1.5, window_s: 61 }, working_on: { mean_pct: 9, window_s: 61 }, working_off: { mean_pct: 5, window_s: 61 } },
    field: { updates_per_s: 5.123, hz: 9, span_s: 40 },
  },
  ...over,
})

test('buildManifest: the locked shape, the fixed budget, rounded CPU, every swatched row counted', () => {
  const m = buildManifest(input()) as Record<string, any>
  assert.deepEqual(m.perf.budget, { idle_pp: 1.0, working_pp: 6.0 })
  assert.deepEqual(m.perf.idle, { on_pct: 2, off_pct: 1.5 })
  assert.equal(m.perf.working.field_updates_per_s, 5.12)
  assert.equal(m.perf.sessions, 8); assert.equal(m.perf.window_s, 60)
  assert.equal(m.capture.rows_total, m.capture.rows_with_swatch)
  assert.deepEqual(Object.keys(m.field_pixels), ['resting', 'working', 'needs_you', 'error'])
  assert.equal(m.plugin_js_sha256, 'p'); assert.equal(m.raw.root, 'evidence/v2/raw')
  assert.deepEqual(m.raw.cpu_order, ['idle_on', 'idle_off', 'working_off', 'working_on'])
  assert.equal(m.raw.cpu.working_on, 'cpu/working_on.csv')
  assert.ok(Math.abs(m.extra.error_vs_resting_mean_dL - 0.002) < 1e-12)
  assert.equal('vision' in m, false, 'the vision block is the conductor\'s, never ours')
})
test('buildManifest refuses missing measurements instead of defaulting them', () => {
  const i = input(); delete (i.measured.pixels as Record<string, Pixels>).error
  assert.throws(() => buildManifest(i), /no measured pixels for error/)
  const j = input(); delete j.measured.cpu.idle_off
  assert.throws(() => buildManifest(j), /no CPU window idle_off/)
})

test('uncovered counts the messages that still show a part outside every exclusion', () => {
  const region: [number, number, number, number] = [0, 0, 100, 100]
  const ex: [number, number, number, number][] = [[0, 0, 50, 50]]
  const box = (x: number, y: number) => ({ x, y, w: 10, h: 10 })
  assert.equal(uncovered([[box(5, 5)]], ex, region), 0)
  assert.equal(uncovered([[box(5, 5)], [box(60, 60)]], ex, region), 1)
  assert.equal(uncovered([[box(5, 5), box(60, 60)]], ex, region), 1, 'one message counts once however many parts show')
  assert.equal(uncovered([[box(200, 5)]], ex, region), 0, 'a part off the region is not measured')
  assert.equal(uncovered([[{ x: 40, y: 40, w: 30, h: 30 }]], ex, region), 1, 'half covered is not covered')
  assert.equal(uncovered([], ex, region), 0)
  assert.equal(uncovered([[]], ex, region), 0)
})
