// Python oracle -> TS parity: EXACT glyph + rgb per organ on every golden scene
// (fixtures/dots-vectors.json, written by tools/gen-dots-vectors.py from python/domain/dots.py).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { renderScene } from '../domain/pattern.ts';

interface Scene { seed: string; hue: number | null; state: string; scale: string; cols: number; rows: number; density: number; twinkle: boolean; entered: number; t: number; cells: [number, number, string, number, number, number, string][] }
const doc = JSON.parse(readFileSync(new URL('./../fixtures/dots-vectors.json', import.meta.url), 'utf8')) as { scenes: Scene[] };

test('the vector file is the size the contract demands: >= 2000 scenes, 7 states + degraded, 3 scales, >= 3 sessions, several t', () => {
  const s = doc.scenes;
  assert.ok(s.length >= 2000, String(s.length));
  assert.deepEqual([...new Set(s.map(x => x.state))].sort(), ['degraded', 'fault', 'idle', 'needs-you', 'review', 'thinking', 'tool', 'unknown']);
  assert.deepEqual([...new Set(s.map(x => x.scale))].sort(), ['M', 'S', 'XL']);
  assert.ok(new Set(s.map(x => x.seed)).size >= 3);
  assert.ok(new Set(s.map(x => x.t)).size >= 8);
});

test('EXACT parity: every organ of every golden scene has the oracle glyph and rgb', () => {
  // Scenes of one configuration share a trajectory; group them so each is simulated once (as the generator did).
  const groups = new Map<string, Scene[]>();
  for (const s of doc.scenes) {
    const k = JSON.stringify([s.seed, s.hue, s.state, s.cols, s.rows, s.density, s.twinkle, s.entered]);
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(s);
  }
  let scenes = 0, organs = 0;
  for (const g of groups.values()) {
    const a = g[0];
    const got = renderScene({ seed: a.seed, hue: a.hue, state: a.state, cols: a.cols, rows: a.rows, entered: a.entered, times: g.map(s => s.t), density: a.density, twinkle: a.twinkle });
    g.forEach((s, i) => {
      const mine = got[i].map(c => [c.x, c.y, c.glyph, c.rgb[0], c.rgb[1], c.rgb[2], c.pigment]);
      assert.deepEqual(mine, s.cells, `${s.state}/${s.scale}/${s.seed} t=${s.t}`);
      scenes++; organs += s.cells.length;
    });
  }
  assert.equal(scenes, doc.scenes.length);
  assert.ok(organs > 50000, `only ${organs} organs compared`);
});

test('red-proof: the comparison can fail (one planted glyph / one rgb channel off => deepEqual throws)', () => {
  const a = doc.scenes.find(s => s.state === 'tool' && s.scale === 'XL' && s.cells.length > 5)!;
  const [cells] = renderScene({ seed: a.seed, hue: a.hue, state: a.state, cols: a.cols, rows: a.rows, entered: a.entered, times: [a.t], density: a.density });
  const mine = cells.map(c => [c.x, c.y, c.glyph, c.rgb[0], c.rgb[1], c.rgb[2], c.pigment]);
  assert.deepEqual(mine, a.cells);                                   // green on the real vector
  const badGlyph = structuredClone(a.cells); badGlyph[0][2] = badGlyph[0][2] === '●' ? '·' : '●';
  const badRgb = structuredClone(a.cells); badRgb[1][4] = (badRgb[1][4] as number) ^ 1;
  assert.throws(() => assert.deepEqual(mine, badGlyph));
  assert.throws(() => assert.deepEqual(mine, badRgb));
});
