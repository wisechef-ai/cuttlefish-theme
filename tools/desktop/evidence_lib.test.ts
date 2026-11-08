import assert from 'node:assert/strict'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { test } from 'node:test'

import {
  clipRects, cpuPct, csvOf, listRawFiles, parseStatTicks, roleOf, sha256Hex, unionCoverage, windowFacts,
} from './evidence_lib.ts'

test('parseStatTicks: utime+stime, tolerating spaces and parens in the command name', () => {
  assert.equal(parseStatTicks('1234 (electron) S 1 1 1 0 -1 4194560 100 0 0 0 70 30 0 0 20 0 1 0 1 1 1'), 100)
  assert.equal(parseStatTicks('9 (Web Content (x)) S 1 1 1 0 -1 0 0 0 0 0 5 7 0 0 20 0 1 0 1 1 1'), 12)
})
test('parseStatTicks rejects what is not a stat line', () => {
  for (const bad of ['', 'garbage', '1 (x) S 1', '1 (x) S ' + 'a '.repeat(30)]) assert.equal(parseStatTicks(bad), null, bad)
})

test('cpuPct: percent of ONE core, 100 ticks/s', () => {
  assert.equal(cpuPct(0, 100, 1), 100)
  assert.equal(cpuPct(100, 150, 2), 25)
  assert.equal(cpuPct(5, 5, 1), 0)
})
test('cpuPct rejects a non-positive interval and a counter that went backwards', () => {
  assert.throws(() => cpuPct(0, 1, 0), /interval/)
  assert.throws(() => cpuPct(0, 1, -1), /interval/)
  assert.throws(() => cpuPct(10, 9, 1), /backwards/)
})

test('roleOf reads the chromium --type flag; the app root is main', () => {
  assert.equal(roleOf('/x/electron --type=renderer --lang=en-US', false), 'renderer')
  assert.equal(roleOf('/x/electron --type=gpu-process --disable-gpu', false), 'gpu')
  assert.equal(roleOf('/x/electron /app --disable-gpu', true), 'main')
  assert.equal(roleOf('/x/electron --type=utility --utility-sub-type=network', false), null)
  assert.equal(roleOf('/x/electron --type=zygote', false), null)
  assert.equal(roleOf('/x/electron /app', false), null, 'only the app root pid is main')
})

test('csvOf writes the exact header and one row per record', () => {
  assert.equal(csvOf(['pid', 'ts', 'cpu_pct'], [[1, 2.5, 3], [4, 5, 6.25]]), 'pid,ts,cpu_pct\n1,2.5,3\n4,5,6.25\n')
  assert.equal(csvOf(['a'], []), 'a\n')
})

test('sha256Hex of a string and of bytes agree', () => {
  assert.equal(sha256Hex('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  assert.equal(sha256Hex(Buffer.from('abc')), sha256Hex('abc'))
})

test('clipRects: clips to the region, makes them region-independent integers, drops empties and off-region boxes', () => {
  const r = clipRects([{ x: 10.4, y: 20.6, w: 100, h: 50 }, { x: -5, y: -5, w: 20, h: 20 }, { x: 900, y: 900, w: 10, h: 10 }, { x: 5, y: 5, w: 0, h: 9 }],
    [0, 0, 800, 600], 2)
  assert.deepEqual(r, [[8, 18, 105, 55], [0, 0, 17, 17]])
})
test('clipRects pads on every side and never leaves the still', () => {
  assert.deepEqual(clipRects([{ x: 0, y: 0, w: 10, h: 10 }], [0, 0, 100, 100], 5), [[0, 0, 15, 15]])
})
test('unionCoverage counts overlapping pixels once', () => {
  assert.equal(unionCoverage([[0, 0, 10, 10], [5, 0, 10, 10]]), 150)
  assert.equal(unionCoverage([]), 0)
})

test('windowFacts: first/last/gaps of a sampled window', () => {
  assert.deepEqual(windowFacts([10, 11, 12.5, 14]), { first: 10, last: 14, span: 4, maxGap: 1.5 })
  assert.throws(() => windowFacts([1]), /two samples/)
})

test('listRawFiles: every file, sorted, with the sha256 of its bytes, relative posix paths', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'cf-raw-'))
  fs.mkdirSync(path.join(d, 'dom')); fs.mkdirSync(path.join(d, 'cpu'))
  fs.writeFileSync(path.join(d, 'dom', 'b.json'), 'abc'); fs.writeFileSync(path.join(d, 'cpu', 'a.csv'), 'abc')
  const got = listRawFiles(d)
  assert.deepEqual(got.map(f => f.path), ['cpu/a.csv', 'dom/b.json'])
  assert.equal(got[0].sha256, sha256Hex('abc'))
  fs.rmSync(d, { recursive: true })
})

test('parseStatTicks: 20 fields after the comm is a stat line, 19 is not; utime and stime must both be numbers', () => {
  const fields = (n: number, u = '70', s = '30') => Array.from({ length: n }, (_, i) => (i === 0 ? 'S' : i === 11 ? u : i === 12 ? s : '0')).join(' ')
  assert.equal(parseStatTicks(`1 (x) ${fields(20)}`), 100)
  assert.equal(parseStatTicks(`1 (x) ${fields(19)}`), null)
  assert.equal(parseStatTicks(`1 (x) ${fields(20, 'x', '30')}`), null)
  assert.equal(parseStatTicks(`1 (x) ${fields(20, '70', 'y')}`), null)
  assert.equal(parseStatTicks(`) ${fields(20, '5', '6')}`), 11, 'a ")" at index 0 still ends the comm')
})

test('clipRects: a box that only touches the region edge, or has no height left, is dropped; clipping applies on the far edges too', () => {
  const region: [number, number, number, number] = [10, 10, 100, 50]
  assert.deepEqual(clipRects([{ x: 110, y: 20, w: 5, h: 5 }], region, 0), [], 'touching the right edge: no pixels')
  assert.deepEqual(clipRects([{ x: 20, y: 60, w: 5, h: 5 }], region, 0), [], 'touching the bottom edge: no pixels')
  assert.deepEqual(clipRects([{ x: 100, y: 50, w: 30, h: 30 }], region, 0), [[100, 50, 10, 10]])
  assert.deepEqual(clipRects([{ x: 5, y: 5, w: 10, h: 10 }], region, 0), [[10, 10, 5, 5]])
  assert.deepEqual(clipRects([{ x: 20, y: 20, w: 1, h: 1 }], region, 0), [[20, 20, 1, 1]])
  assert.deepEqual(clipRects([{ x: 20, y: 20, w: 1, h: 0.0001 }], region, 0), [[20, 20, 1, 1]], 'a sliver rounds out to a whole pixel')
})

test('unionCoverage: 2-D overlaps are counted once (distinct pixels never collide)', () => {
  assert.equal(unionCoverage([[0, 0, 2, 2], [1, 1, 2, 2]]), 7)
  assert.equal(unionCoverage([[0, 1, 1, 1], [1, 0, 1, 1]]), 2)
  assert.equal(unionCoverage([[3, 0, 1, 1], [0, 3, 1, 1], [0, 0, 1, 1]]), 3)
})

test('windowFacts: the largest gap may be the last one, and may be below 1', () => {
  assert.deepEqual(windowFacts([0, 1, 5]), { first: 0, last: 5, span: 5, maxGap: 4 })
  assert.deepEqual(windowFacts([2, 2.5, 3]), { first: 2, last: 3, span: 1, maxGap: 0.5 })
})

test('listRawFiles sorts by path whatever order the directory lists them in', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'cf-raw2-'))
  const names = Array.from({ length: 24 }, (_, i) => `${['z', 'a', 'm', 'q'][i % 4]}${(i * 7) % 24}.txt`)
  for (const n of names) fs.writeFileSync(path.join(d, n), n)
  fs.mkdirSync(path.join(d, 'b')); fs.writeFileSync(path.join(d, 'b', 'x'), 'x'); fs.writeFileSync(path.join(d, 'b', 'a'), 'a')
  const got = listRawFiles(d).map(f => f.path)
  assert.deepEqual(got, [...got].sort())
  assert.equal(got.length, 26)
  fs.rmSync(d, { recursive: true })
})

test('clipRects drops a box with no height as well as one with no width; windowFacts accepts exactly two samples', () => {
  assert.deepEqual(clipRects([{ x: 5, y: 5, w: 9, h: 0 }], [0, 0, 100, 100], 2), [])
  assert.deepEqual(clipRects([{ x: 5, y: 5, w: 0, h: 9 }], [0, 0, 100, 100], 2), [])
  assert.deepEqual(windowFacts([1, 3]), { first: 1, last: 3, span: 2, maxGap: 2 })
})

// ---- ev3: the small-window exclusion rule, the strip verdict, sidebar crops, the centre pick -------------------------------
import {
  MAX_EXCLUDED_SHARE, MIN_MEASURED_PX, centreDistance, cropFilter, exclusionVerdict, sidebarRect, stripVerdict,
} from './evidence_lib.ts'

test('exclusionVerdict: within the 25 % share passes and reports both numbers', () => {
  const v = exclusionVerdict(1_000_000, 200_000)
  assert.equal(v.ok, true); assert.equal(v.reason, null)
  assert.equal(v.share, 0.2); assert.equal(v.measured, 800_000)
})
test('exclusionVerdict: a small window over 25 % passes while enough area remains (the reason says so)', () => {
  const area = 400_000, excluded = 112_000 // 28 %, like the 1280x800 run; 288 000 px left
  const v = exclusionVerdict(area, excluded)
  assert.equal(v.ok, true)
  assert.ok(v.share > MAX_EXCLUDED_SHARE)
  assert.equal(v.measured, 288_000)
  assert.match(v.reason ?? '', /small window: 28% excluded .*288000 px measured/)
})
test('exclusionVerdict: fails when the remaining measured area is below the minimum, whatever the share', () => {
  const v = exclusionVerdict(300_000, 150_000) // 50 % excluded, 150 000 px left (< MIN)
  assert.equal(v.ok, false)
  assert.match(v.reason ?? '', /too little field left to measure/)
  assert.equal(MIN_MEASURED_PX, 200_000, 'the floor is fixed here, not tuned to a run')
  assert.equal(exclusionVerdict(1_000_000, 999_000).ok, false, 'a sliver of field is refused even at the 1600x1000 size')
})
test('exclusionVerdict: the exact boundaries — 25 % is ok, MIN measured px is ok, one px less is not', () => {
  assert.equal(exclusionVerdict(1_000_000, 250_000).reason, null)
  assert.equal(exclusionVerdict(1_000_000, 250_000).ok, true)
  assert.equal(exclusionVerdict(400_000, 200_000).ok, true, `exactly ${MIN_MEASURED_PX} px left is measurable`)
  assert.equal(exclusionVerdict(400_000, 200_001).ok, false)
  assert.throws(() => exclusionVerdict(0, 0), /area must be positive/)
})

test('stripVerdict: inside the viewport and not truncated', () => {
  const v = stripVerdict({ box: { x: 10, y: 700, w: 900, h: 22 }, viewport: { w: 1280, h: 800 }, truncated: false, textOverflow: 'ellipsis' })
  assert.deepEqual(v, { box: { x: 10, y: 700, w: 900, h: 22 }, inside: true, clipped: false, text_overflow: 'ellipsis' })
})
test('stripVerdict: a box past the right or bottom edge is outside; a truncated strip is clipped', () => {
  assert.equal(stripVerdict({ box: { x: 1000, y: 0, w: 300, h: 20 }, viewport: { w: 1280, h: 800 }, truncated: false, textOverflow: '' }).inside, false)
  assert.equal(stripVerdict({ box: { x: 0, y: 790, w: 20, h: 20 }, viewport: { w: 1280, h: 800 }, truncated: false, textOverflow: '' }).inside, false)
  assert.equal(stripVerdict({ box: { x: 0, y: 0, w: 1280, h: 20 }, viewport: { w: 1280, h: 800 }, truncated: true, textOverflow: 'clip' }).clipped, true)
})
test('stripVerdict: no strip element at all is a failure to report, not a pass', () => {
  const v = stripVerdict({ box: null, viewport: { w: 1280, h: 800 }, truncated: false, textOverflow: '' })
  assert.equal(v.inside, false); assert.equal(v.box, null)
})

test('sidebarRect: the padded union of the rows, clipped to the screen', () => {
  const rows = [{ x: 20, y: 60, w: 200, h: 30 }, { x: 24, y: 300, w: 190, h: 30 }]
  assert.deepEqual(sidebarRect(rows, { w: 1280, h: 800 }, 6), [14, 54, 212, 282])
  assert.deepEqual(sidebarRect([{ x: -10, y: -10, w: 40, h: 40 }], { w: 1280, h: 800 }, 6), [0, 0, 36, 36])
  assert.equal(sidebarRect([], { w: 1280, h: 800 }, 6), null)
})
test('cropFilter: a crop then a nearest-neighbour upscale (crisp pixels, no blur)', () => {
  assert.equal(cropFilter([14, 54, 206, 282], 2), 'crop=206:282:14:54,scale=iw*2:ih*2:flags=neighbor')
  assert.throws(() => cropFilter([0, 0, 0, 5], 2), /empty crop/)
})
test('centreDistance: 0 at the centre, 1 at the middle of an edge, normalised per axis', () => {
  const r: [number, number, number, number] = [100, 200, 400, 200]
  assert.equal(centreDistance(300, 300, r), 0)
  assert.equal(centreDistance(500, 300, r), 1)
  assert.equal(centreDistance(300, 400, r), 1)
  assert.ok(Math.abs(centreDistance(400, 300, r) - 0.5) < 1e-12)
})
