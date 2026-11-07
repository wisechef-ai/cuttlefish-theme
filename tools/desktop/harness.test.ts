import assert from 'node:assert/strict'
import { test } from 'node:test'

import { assertOutsideLive, parseListen, recordIsolation, startXvfb } from './harness.ts'

const SS = `State  Recv-Q Send-Q  Local Address:Port  Peer Address:PortProcess
LISTEN 0      2048        127.0.0.1:40749      0.0.0.0:*    users:(("hermes",pid=714839,fd=7))
LISTEN 0      4096             [::]:22            [::]:*
LISTEN 0      5           127.0.0.1:3245       0.0.0.0:*    users:(("python",pid=1815583,fd=10))`

test('parseListen reads port, pid and process; skips header', () => {
  const r = parseListen(SS)
  assert.deepEqual(r.map(x => x.port), [40749, 22, 3245])
  assert.equal(r[0].pid, 714839); assert.equal(r[0].proc, 'hermes'); assert.equal(r[1].pid, null)
})
test('parseListen rejects garbage lines', () => assert.deepEqual(parseListen('nonsense\nESTAB 0 0 a:1 b:2'), []))

const sb = (root: string) => ({ root, hermesHome: `${root}/hermes-home`, userDataDir: `${root}/electron-user-data` })
test('assertOutsideLive refuses the live home and ~/.config', () => {
  assert.throws(() => assertOutsideLive(sb(`${process.env.HOME}/.hermes/x`)), /inside live/)
  assert.throws(() => assertOutsideLive(sb(`${process.env.HOME}/.config/y`)), /inside live/)
  assert.doesNotThrow(() => assertOutsideLive(sb('/tmp/cf-ok')))
})
test('startXvfb refuses :0 :1 and non-private displays', async () => {
  for (const d of [':0', ':1', ':10', 'x']) await assert.rejects(startXvfb(d), /refusing display/)
})
test('recordIsolation throws when the gateway port collides with a live Hermes port', () => {
  const base = { sandbox: sb('/tmp/cf-ok'), display: ':93', sha: 'abc' }
  const live = [{ port: 40749, pid: 1, proc: 'hermes' }]
  assert.throws(() => recordIsolation(base, live, [{ port: 40749, pid: 2, proc: 'python' }]), /isolation violated/)
  assert.throws(() => recordIsolation(base, live, []), /isolation violated/, 'no gateway found is not isolation proof')
  assert.throws(() => recordIsolation({ ...base, display: ':0' }, live, [{ port: 5, pid: 2, proc: 'p' }]), /isolation violated/)
  const ok = recordIsolation(base, live, [{ port: 5, pid: 2, proc: 'p' }])
  assert.equal(ok.gateway_port_disjoint_from_live, true); assert.equal(ok.isolated_backend, true)
})
