// Unit: the hash every deterministic choice flows through. Vectors embedded from
// origin/v22 packages/core/fixtures/blake2b-vectors.json (generated with python hashlib,
// i.e. the RFC 7693 reference behaviour) — reuse per the lane brief's reuse rule.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { blake2b, seededStream, utf8 } from '../../src/domain/blake2b.ts'

const hex = (u: Uint8Array): string => Array.from(u, b => b.toString(16).padStart(2, '0')).join('')

const VECTORS: { msg: string; size: number; digest: string }[] = [
  { msg: '', size: 32, digest: '0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8' },
  { msg: 'abc', size: 64, digest: 'ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d17d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923' },
  {
    msg: 'л δцл рβ ΨΨ иβδцлииррилиц рαΨγиΩилиδрлγγ γлиδи лрδкрγ ццлиγαβииррлцаββкцаиΨΨΩлβаираβγликиγγклΩΨкииδδииΨ Ψ βил αцилиΩии  Ωл ΩцаαиилγрΨкΨрαаαкδллβγ лрка  ика и цил γрииβΩαрΨа γββиΨδΨαаδииδΩцаγирβлаΩΩлии',
    size: 32, digest: 'ed3bba830d06fba97f52f0a46106ed33976cfd59dfedccce589345ad265256bc',
  },
  {
    msg: 'ç-40xjémwésć6Öójv8óuąpl9ń2ót1Üs6ełhÖe0meiyi0hrñ2ñvép2fzińm0lbßxą',
    size: 32, digest: '88cb126abf9bd38f99c30334c399556175bdac7289c6cba6dbb0b1e5580283a8',
  },
]

test('blake2b matches the reference vectors (empty, ascii, two-byte, latin-1 input)', () => {
  for (const v of VECTORS) assert.equal(hex(blake2b(utf8(v.msg), v.size)), v.digest, `msg=${JSON.stringify(v.msg.slice(0, 20))}…`)
})

test('every digest size 1..64 is honoured and deterministic', () => {
  const data = utf8('cuttlefish')
  for (let n = 1; n <= 64; n++) {
    const d = blake2b(data, n)
    assert.equal(d.length, n)
    assert.deepEqual(blake2b(data, n), d, `size ${n} not deterministic`)
  }
})

test('distinct inputs give distinct hashes', () => {
  const a = hex(blake2b(utf8('a'), 32)), b = hex(blake2b(utf8('b'), 32))
  assert.notEqual(a, b)
})

test('seededStream: deterministic, in [0,1), and separated by domain', () => {
  const s1 = seededStream('root-1', 'constellation')
  const s2 = seededStream('root-1', 'constellation')
  const other = seededStream('root-1', 'twinkle')
  const a: number[] = [], b: number[] = [], c: number[] = []
  for (let i = 0; i < 200; i++) { a.push(s1()); b.push(s2()); c.push(other()) }
  assert.deepEqual(a, b, 'same seed+domain must give the same stream')
  assert.ok(a.every(x => x >= 0 && x < 1), 'stream values must lie in [0,1)')
  assert.notDeepEqual(a, c, 'a different domain must give a different stream')
  assert.ok(new Set(a.slice(0, 32)).size > 20, 'a stream this short should not repeat values heavily')
})
