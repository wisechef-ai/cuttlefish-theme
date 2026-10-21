import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import * as index from '../index.ts';

test('index.ts bundles into ONE self-contained ESM module (no imports, no node: builtins) with the same exports', async () => {
  const r = await build({ entryPoints: [new URL('../index.ts', import.meta.url).pathname], bundle: true, format: 'esm', platform: 'neutral', write: false, metafile: true, logLevel: 'silent' });
  const code = r.outputFiles[0].text;
  assert.deepEqual(r.metafile.outputs[Object.keys(r.metafile.outputs)[0]].imports, [], 'bundle has external imports');
  assert.ok(!/\bfrom\s*["']node:/.test(code) && !/require\(/.test(code));
  const mod = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
  assert.deepEqual(Object.keys(mod).sort(), Object.keys(index).sort());
});

test('the bundled core renders (blake2b + identity + pattern run with no host APIs)', async () => {
  const r = await build({ entryPoints: [new URL('../index.ts', import.meta.url).pathname], bundle: true, format: 'esm', platform: 'neutral', write: false, logLevel: 'silent' });
  const mod: any = await import('data:text/javascript;base64,' + Buffer.from(r.outputFiles[0].text).toString('base64'));
  const hue = mod.allocate('20260930_104729_led', []).hue_deg;
  const m = mod.renderModel({ session: { name: 'ledger', hue_deg: hue }, state: 'idle', scale: 'S', w: 4, h: 2, now: 0, focused: true, visible: true, reducedMotion: false });
  assert.ok(m.cells.length >= 1 && m.cells.every((c: any) => c.rgb.length === 3), 'the bundled core scatters organs with no host APIs');
  assert.equal(m.pixels, undefined, 'no pixel buffer: D2 has no ground to paint');
});
