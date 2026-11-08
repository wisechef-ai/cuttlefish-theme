/**
 * Public-repo hygiene (dev tooling): no tracked file carries a user home path, a tailnet (CGNAT) range address or the private
 * capture host's name. Scans every tracked file (git ls-files; .git is never listed) and fails on any hit that is not in ALLOWED.
 * The patterns are spelled in pieces so this file does not match itself. History is NOT scanned (only what HEAD tracks).
 */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
export const PATTERNS: { name: string; re: RegExp }[] = [
  { name: 'user home path', re: new RegExp('/ho' + 'me/[^/\\s"\']+') },
  { name: 'tailnet (CGNAT) range address', re: /\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b/ },
  { name: 'private capture host', re: new RegExp('herc' + 'ules', 'i') },
]
/** Lines that already matched before this lane, in files this lane does not own (locked contract, product tests, reviews).
 *  The exact number of matching lines allowed per file: one more anywhere, or in a file not listed, fails. Remove entries as the files are fixed. */
export const ALLOWED: Record<string, number> = {
  'desktop/test/acceptance/traces/README.md': 1, // LOCKED (desktop/test/acceptance/**): a grep pattern for the trace redaction check
  'tests/acceptance/helpers.py': 2, // CF_HERMES_CORE and the default interpreter path (locked contract)
  'tests/acceptance/test_instruments_py.py': 1, // NODE_FALLBACK default (locked contract)
  'tests/acceptance/test_o8_submission_kit.py': 1, // CF_KIT_DIR default (locked contract)
}

/** The (pattern name) hits of every line of `text`: [lineNumber, patternName][]. */
export function scanText(text: string): [number, string][] {
  const out: [number, string][] = []
  text.split('\n').forEach((line, i) => { for (const p of PATTERNS) if (p.re.test(line)) out.push([i + 1, p.name]) })
  return out
}

function trackedFiles(): string[] {
  return execFileSync('git', ['-C', ROOT, 'ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean)
}

test('the scanner finds each pattern and nothing that merely looks like one', () => {
  assert.deepEqual(scanText('cd /ho' + 'me/someone/repos'), [[1, 'user home path']])
  assert.deepEqual(scanText('ssh 100.' + '106.27.136'), [[1, 'tailnet (CGNAT) range address']])
  assert.deepEqual(scanText('the ' + 'herc' + 'ules box'), [[1, 'private capture host']])
  assert.deepEqual(scanText('100.63.0.1 and 10.0.0.1 and home/ and /home without a user'), [])
})

test('every tracked file is clean, except the counted legacy hits in ALLOWED', () => {
  const files = trackedFiles()
  assert.ok(files.includes('tools/desktop/hygiene.test.ts'), 'the scan sees the tracked tree')
  const found: Record<string, string[]> = {}
  for (const rel of files) {
    const text = fs.readFileSync(path.join(ROOT, rel)).toString('latin1')
    const hits = scanText(text)
    if (hits.length) found[rel] = hits.map(([l, n]) => `${l}:${n}`)
  }
  const problems: string[] = []
  for (const [rel, hits] of Object.entries(found)) {
    const allowed = ALLOWED[rel] ?? 0
    if (hits.length !== allowed) problems.push(`${rel}: ${hits.length} hit line(s), allowed ${allowed}: ${hits.join(', ')}`)
  }
  for (const [rel, n] of Object.entries(ALLOWED)) if (!found[rel]) problems.push(`${rel}: listed in ALLOWED (${n}) but clean now: remove it`)
  console.log(`hygiene: scanned ${files.length} tracked files, ${Object.values(found).reduce((a, h) => a + h.length, 0)} hit line(s) in ${Object.keys(found).length} file(s)`)
  assert.deepEqual(problems, [], problems.join('\n'))
})
