// Type-only contract of the shipped entry: the plugin's shape (A1) and the
// SDK-facing files (runtime, surfaces) typecheck as part of this suite's
// program — they are never imported at runtime here, so the SDK is only ever
// needed by the shipped bundle, exactly like the loader's allowlist.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import type { CfPlugin } from '../../../src/index.ts'

test('types: the entry is one plugin object with the locked shape', () => {
  const probe: CfPlugin = {
    id: 'cuttlefish-theme',
    name: 'Cuttlefish',
    description: 'words',
    register: () => {},
  }
  assert.equal(probe.id, 'cuttlefish-theme')
  assert.equal(typeof probe.register, 'function')
})
