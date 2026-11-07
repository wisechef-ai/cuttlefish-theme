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
