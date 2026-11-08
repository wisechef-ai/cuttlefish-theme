import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildManifest, uncovered, type ManifestInput, type Pixels } from './manifest.ts'

const px = (m: number): Pixels => ({ organs_detected: 30, p95_dL: 0.03, mean_dL: m, lowK: 0.1, highK: 0.7 })
const input = (over: Partial<ManifestInput> = {}): ManifestInput => ({
  commit: 'c', pluginSha: 'p', core: { version: 'v0.22.7', sha: 'b200f5bc60e', desktop_build: 'source' }, isolation: { gateway_port: 5 },
  video: { path: 'evidence/v2/capture.mp4', sha256: 'v', start_epoch: 1 },
  stripCheck: { viewport: { w: 1600, h: 1000 }, states: [{ session: 's', state: 'resting', box: { x: 1, y: 2, w: 3, h: 4 }, inside: true, clipped: false, text_overflow: '' }] },
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

test('uncovered: edges are exact — flush with an exclusion is covered, a pixel beyond is shown, touching the region edge shows nothing', () => {
  const region: [number, number, number, number] = [0, 0, 100, 100]
  const ex: [number, number, number, number][] = [[10, 10, 20, 20]]
  const part = (x: number, y: number, w: number, h: number) => [[{ x, y, w, h }]]
  assert.equal(uncovered(part(10, 10, 20, 20), ex, region), 0, 'exactly the exclusion')
  assert.equal(uncovered(part(9, 10, 20, 20), ex, region), 1, 'one pixel left of it')
  assert.equal(uncovered(part(10, 9, 20, 20), ex, region), 1, 'one pixel above it')
  assert.equal(uncovered(part(11, 10, 20, 20), ex, region), 1, 'one pixel past its right edge')
  assert.equal(uncovered(part(10, 11, 20, 20), ex, region), 1, 'one pixel past its bottom edge')
  assert.equal(uncovered(part(12, 12, 5, 5), ex, region), 0)
  assert.equal(uncovered(part(100, 5, 10, 10), ex, region), 0, 'starts where the region ends')
  assert.equal(uncovered(part(5, 100, 10, 10), ex, region), 0, 'starts where the region ends (y)')
  assert.equal(uncovered(part(-10, 5, 10, 10), ex, region), 0, 'ends where the region starts')
  assert.equal(uncovered(part(5, -10, 10, 10), ex, region), 0, 'ends where the region starts (y)')
  assert.equal(uncovered(part(10, 10, 20, 40), ex, region), 1, 'covered along x only')
  assert.equal(uncovered(part(10, 10, 60, 20), ex, region), 1, 'covered along y only')
  assert.equal(uncovered(part(90, 90, 30, 30), [[90, 90, 10, 10]], region), 0, 'clipped to the region first, then covered')
})

test('buildManifest: the extra block reports the idle still, bloom stills and both grounds; absent ones are null / omitted', () => {
  const full = input()
  full.measured.pixels['resting-idle'] = { ...px(0.02), ground: '#fefefe' }
  full.measured.pixels['needs_you.bloom'] = px(0.09)
  full.measured.pixels.resting.ground = '#fefefe'
  for (const s of ['resting', 'working', 'needs_you', 'error']) full.measured.pixels[`dark.${s}`] = { ...px(0.01), ground: '#141416' }
  full.measured.pixels['dark.error'] = { ...px(0.03), ground: '#141416' }
  const x = (buildManifest(full) as Record<string, any>).extra
  assert.equal(x.resting_idle.mean_dL, 0.02)
  assert.deepEqual(Object.keys(x.bloom), ['needs_you.bloom'])
  assert.equal(x.grounds.default.ground, '#fefefe'); assert.equal(x.grounds.dark.ground, '#141416')
  assert.ok(Math.abs(x.grounds.dark.error_minus_resting_mean_dL - 0.02) < 1e-12, 'error − resting, not resting − error')
  assert.ok(Math.abs(x.grounds.default.error_minus_resting_mean_dL - 0.002) < 1e-12)
  assert.deepEqual(Object.keys(x.grounds.dark.mean_dL), ['resting', 'working', 'needs_you', 'error'])
  const bare = (buildManifest(input()) as Record<string, any>).extra
  assert.equal(bare.resting_idle, null); assert.deepEqual(bare.bloom, {}); assert.deepEqual(Object.keys(bare.grounds), ['default'])
  assert.equal(bare.grounds.default.ground, null, 'no ground measured: null, never invented')
  const partial = input(); partial.measured.pixels['dark.resting'] = px(0.01); partial.measured.pixels['dark.error'] = px(0.02)
  const p = (buildManifest(partial) as Record<string, any>).extra.grounds.dark
  assert.equal(p.mean_dL.working, null); assert.equal(p.mean_dL.needs_you, null)
})

test('buildManifest: a ground with no resting or no error still is not reported', () => {
  const only = input(); only.measured.pixels['dark.resting'] = px(0.01)
  assert.deepEqual(Object.keys((buildManifest(only) as Record<string, any>).extra.grounds), ['default'])
  const other = input(); other.measured.pixels['dark.error'] = px(0.01)
  assert.deepEqual(Object.keys((buildManifest(other) as Record<string, any>).extra.grounds), ['default'])
})

test('uncovered reads an exclusion as [x, y, w, h], not symmetrically', () => {
  const region: [number, number, number, number] = [0, 0, 200, 200]
  const ex: [number, number, number, number][] = [[10, 40, 20, 30]] // x 10..30, y 40..70
  const part = (x: number, y: number, w: number, h: number) => [[{ x, y, w, h }]]
  assert.equal(uncovered(part(10, 40, 20, 30), ex, region), 0)
  assert.equal(uncovered(part(10, 40, 30, 20), ex, region), 1, 'w and h swapped sticks out to the right')
  assert.equal(uncovered(part(40, 10, 30, 20), ex, region), 1, 'x and y swapped is somewhere else')
  assert.equal(uncovered(part(10, 40, 20, 31), ex, region), 1)
  assert.equal(uncovered(part(10, 20, 20, 10), ex, region), 1, 'above the exclusion, below its x')
})

test('buildManifest keeps a legitimate zero / empty measurement instead of turning it into null', () => {
  const m = input(); m.measured.pixels['dark.resting'] = { ...px(0), ground: '' }; m.measured.pixels['dark.error'] = px(0)
  m.measured.pixels['dark.working'] = px(0)
  const d = (buildManifest(m) as Record<string, any>).extra.grounds.dark
  assert.equal(d.ground, ''); assert.equal(d.mean_dL.working, 0); assert.equal(d.mean_dL.resting, 0)
})

// ---- ev3: strip check per focused state, sidebar crops, the exclusion numbers, and a second window size -----------------------
const strip = (state: string, inside: boolean, clipped: boolean) => ({
  session: 's', state, box: { x: 10, y: 700, w: 900, h: 22 }, inside, clipped, text_overflow: 'ellipsis',
})
test('buildManifest: the strip check per focused state, with the verdicts derived (all inside, any clipped)', () => {
  const ok = buildManifest(input({ stripCheck: { viewport: { w: 1280, h: 800 }, states: [strip('resting', true, false), strip('error', true, false)] } })) as Record<string, any>
  assert.deepEqual(ok.capture.strip_check, { viewport: { w: 1280, h: 800 }, states: [strip('resting', true, false), strip('error', true, false)], all_inside: true, any_clipped: false })
  const bad = buildManifest(input({ stripCheck: { viewport: { w: 1280, h: 800 }, states: [strip('working', false, true)] } })) as Record<string, any>
  assert.equal(bad.capture.strip_check.all_inside, false); assert.equal(bad.capture.strip_check.any_clipped, true)
})
test('buildManifest: an empty strip check is refused, not written as a pass', () => {
  assert.throws(() => buildManifest(input({ stripCheck: { viewport: { w: 1600, h: 1000 }, states: [] } })), /no focused state/)
})
test('buildManifest: sidebar crops are listed with their sha, the finished_unseen still is a still', () => {
  const crops = [{ state: 'finished_unseen', path: 'evidence/v2/raw/stills/sidebar-finished_unseen.png', sha256: 'c', source: 'evidence/v2/raw/stills/finished_unseen.png' }]
  const m = buildManifest(input({ sidebarCrops: crops })) as Record<string, any>
  assert.deepEqual(m.capture.sidebar_crops, crops)
})
test('buildManifest: the exclusion numbers of each still (share and measured px) come from the measurement', () => {
  const ex = { area: 800000, excluded_px: 224000, measured_px: 576000, share: 0.28, reason: 'small window' }
  const i = input(); (i.measured.pixels as Record<string, any>).resting = { ...px(0.01), exclusion: ex }
  const m = buildManifest(i) as Record<string, any>
  assert.deepEqual(m.extra.exclusions, { resting: ex })
})
test('buildManifest: a second window size writes under its own directory (the default stays evidence/v2)', () => {
  const d = buildManifest(input()) as Record<string, any>
  assert.equal(d.raw.root, 'evidence/v2/raw')
  const s = buildManifest(input({ rel: 'evidence/v2-1280x800', video: { path: 'evidence/v2-1280x800/capture.mp4', sha256: 'v', start_epoch: 1 } })) as Record<string, any>
  assert.equal(s.raw.root, 'evidence/v2-1280x800/raw')
  assert.equal(s.capture.video, 'evidence/v2-1280x800/capture.mp4')
})

test('buildManifest scrubs the user home and tailnet addresses at write time: no /home/ and no tailnet IP survive', () => {
  const i = input({ isolation: { hermes_home: '/ho' + 'me/someone/repos/hackathon/sandboxes/evidence-x/hermes-home', host: '100.' + '106.27.136' } })
  const text = JSON.stringify(buildManifest(i))
  assert.equal(text.includes('/ho' + 'me/'), false)
  assert.equal(text.includes('100.' + '106.27.136'), false)
  const m = buildManifest(i) as Record<string, any>
  assert.equal(m.isolation.hermes_home, '<home>/repos/hackathon/sandboxes/evidence-x/hermes-home')
  assert.equal(m.isolation.host, '<tailnet-ip>')
})
