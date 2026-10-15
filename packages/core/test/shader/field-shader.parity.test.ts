// GPU-vs-CPU parity (plan §5 G3 groundwork, §13.2): the XL fragment shader is rendered in headless
// Chromium (WebGL2 via SwiftShader) and compared with the CPU pattern (the oracle) pixel by pixel.
//   exact   : all four channels equal
//   near    : not exact, but every channel within one coverage level (1/3 of the dot-vs-ground span)
// Contract: exact >= 99.5 % and near-or-exact == 100 % in EVERY scene.
// Skipped, with an explicit reason, only when Chromium/Playwright is unavailable; CF_REQUIRE_GPU=1 (set in
// CI) turns that skip into a failure so a green run always means the GPU tests executed.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { paint } from '../../domain/pattern.ts';
import { FIELD_FRAGMENT_SOURCE, FIELD_VERTEX_SOURCE, FIELD_UNIFORM_TYPES, uniformsFor } from '../../domain/field-shader.ts';
import { renderScenes, type HarnessIn, type HarnessOut } from './gl-harness.ts';

const fx = JSON.parse(readFileSync(new URL('../../../../tools/p1/stub-sessions.json', import.meta.url), 'utf8'));
const HUES: number[] = fx.sessions.filter((s: { hue_deg: number | null }) => s.hue_deg != null).slice(0, 4).map((s: { hue_deg: number }) => s.hue_deg);
assert.equal(HUES.length, 4);

// Desktop XL internal size: the P1 host's own function, so the test cannot drift from what hosts paint.
const stub = await import('../../../../tools/p1/hosts/desktop-stub/plugin.js').catch(() => null);
const DESKTOP = stub ? stub.xlPaintSize(720, 780) : { w: 180, h: 195 };
const SIZES: { id: string; w: number; h: number }[] = [
  { id: '320x180', w: 320, h: 180 },
  { id: `desktop ${DESKTOP.w}x${DESKTOP.h}`, w: DESKTOP.w, h: DESKTOP.h },
];
for (const s of SIZES) assert.ok(s.w * s.h <= 57600);

const LOOKS: { id: string; look: string; degraded: boolean; steps: number[] }[] = [
  { id: 'idle', look: 'idle', degraded: false, steps: [0] },
  { id: 'working', look: 'working', degraded: false, steps: [3, 4, 5] },
  { id: 'review', look: 'review', degraded: false, steps: [0] },
  { id: 'needs-you', look: 'needs-you', degraded: false, steps: [0] },
  { id: 'fault', look: 'fault', degraded: false, steps: [0] },
  { id: 'unknown', look: 'unknown', degraded: false, steps: [0] },
  { id: 'degraded', look: 'idle', degraded: true, steps: [0] },
];

// ---- availability ---------------------------------------------------------------------------------
const require = createRequire(new URL('../../../../tools/package.json', import.meta.url));
// Playwright is a tools/-only dependency loaded by createRequire, so it has no types here.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let browser: any = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let page: any = null;
let skipReason: string | false = false;
try {
  const { chromium } = require('playwright');
  browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--use-gl=angle'] });
  page = await browser.newPage();
} catch (e) {
  skipReason = `Chromium/Playwright unavailable (${String((e as Error).message).split('\n')[0]}); run: cd tools && npm ci && npx playwright install chromium`;
  if (process.env.CF_REQUIRE_GPU === '1') throw new Error(`CF_REQUIRE_GPU=1 but ${skipReason}`);
}
after(async () => { if (browser) await browser.close(); });

async function gpu(input: HarnessIn): Promise<HarnessOut> {
  return page.evaluate(renderScenes, input);
}
const decode = (b64: string): Uint8Array => new Uint8Array(Buffer.from(b64, 'base64'));

interface Cmp { exact: number; near: number; total: number; maxDelta: number; tol: number }
function span(u: ReturnType<typeof uniformsFor>): number[] {
  const G = u.uGround as number[];
  const cols: number[][] = [...(u.uDots as number[]).reduce<number[][]>((a, v, i) => { (a[Math.floor(i / 3)] ||= []).push(v); return a; }, []), u.uBlanch as number[], u.uGrey as number[], u.uRed as number[], u.uAmber as number[]];
  return [0, 1, 2].map(ch => Math.max(...cols.map(c => Math.abs(c[ch] - G[ch]))));
}
function compare(cpu: Uint8ClampedArray | Uint8Array, got: Uint8Array, u: ReturnType<typeof uniformsFor>): Cmp {
  const sp = span(u);
  const tol = sp.map(s => Math.ceil(s / 3) + 1);    // one coverage level = span/3; +1 for the independent byte rounding of two colours
  let exact = 0, near = 0, maxDelta = 0;
  const total = cpu.length / 4;
  for (let p = 0; p < total; p++) {
    let ok = true, same = true;
    for (let ch = 0; ch < 4; ch++) {
      const d = Math.abs(cpu[p * 4 + ch] - got[p * 4 + ch]);
      if (d) same = false;
      if (ch < 3) { if (d > maxDelta) maxDelta = d; if (d > tol[ch]) ok = false; } else if (d) ok = false;
    }
    if (same) exact++; else if (ok) near++;
  }
  return { exact, near, total, maxDelta, tol: Math.max(...tol) };
}

interface SceneMeta { key: string; look: string; size: string; hue: number | null; step: number; w: number; h: number; u: ReturnType<typeof uniformsFor>; cpu: Uint8ClampedArray }
function buildScenes(): SceneMeta[] {
  const out: SceneMeta[] = [];
  for (const size of SIZES) for (const L of LOOKS) for (const hue of HUES) for (const step of L.steps) {
    const hueDeg = L.degraded ? null : hue;
    const u = uniformsFor({ look: L.look, hueDeg, step, w: size.w, h: size.h });
    const cpu = paint({ scale: 'XL', w: size.w, h: size.h, look: L.look, hueDeg, name: 'x', alarmText: null, step, reducedMotion: false }).pixels;
    out.push({ key: `${size.id} ${L.id} hue${hue} step${step}`, look: L.id, size: size.id, hue: hueDeg, step, w: size.w, h: size.h, u, cpu });
  }
  return out;
}
const toIn = (scenes: SceneMeta[], fs = FIELD_FRAGMENT_SOURCE, bench: HarnessIn['bench'] = null): HarnessIn =>
  ({ vs: FIELD_VERTEX_SOURCE, fs, types: FIELD_UNIFORM_TYPES, scenes: scenes.map(s => ({ w: s.w, h: s.h, uniforms: s.u })), bench });

// ---- pure (no GPU) --------------------------------------------------------------------------------
test('uniformsFor: static looks ignore the frame step, working follows it, degraded drops identity', () => {
  for (const look of ['idle', 'review', 'needs-you', 'fault', 'unknown']) {
    assert.deepEqual(uniformsFor({ look, hueDeg: 200, step: 0, w: 320, h: 180 }), uniformsFor({ look, hueDeg: 200, step: 977, w: 320, h: 180 }), look);
  }
  assert.notDeepEqual(uniformsFor({ look: 'working', hueDeg: 200, step: 1, w: 320, h: 180 }), uniformsFor({ look: 'working', hueDeg: 200, step: 2, w: 320, h: 180 }));
  assert.deepEqual(uniformsFor({ look: 'working', hueDeg: 200, step: 5, w: 64, h: 64, reducedMotion: true }), uniformsFor({ look: 'working', hueDeg: 200, step: 0, w: 64, h: 64, reducedMotion: true }));
  const d = uniformsFor({ look: 'working', hueDeg: null, step: 3, w: 64, h: 64 });
  assert.equal(d.uLook, 5, 'degraded paints as unknown');
});

// ---- GPU ------------------------------------------------------------------------------------------
test('shader parity vs CPU oracle: every look x 3 working frames x 4 sessions x 2 sizes', { skip: skipReason, timeout: 600_000 }, async () => {
  const scenes = buildScenes();
  const res = await gpu(toIn(scenes, FIELD_FRAGMENT_SOURCE, { w: 320, h: 180, frames: 60, uniforms: uniformsFor({ look: 'working', hueDeg: HUES[0], step: 3, w: 320, h: 180 }) }));
  console.log(`# GPU parity renderer: ${res.renderer} | ${res.version}`);
  assert.equal(res.pixels.length, scenes.length);
  const agg = new Map<string, { exact: number; near: number; total: number; maxDelta: number; n: number; minExactPct: number }>();
  for (let i = 0; i < scenes.length; i++) {
    const s = scenes[i];
    const c = compare(s.cpu, decode(res.pixels[i]), s.u);
    const pct = (100 * c.exact) / c.total;
    assert.ok(pct >= 99.5, `${s.key}: only ${pct.toFixed(3)} % exact (<99.5)`);
    assert.equal(c.exact + c.near, c.total, `${s.key}: ${c.total - c.exact - c.near} pixels beyond one coverage level (max |d| ${c.maxDelta}, tol ${c.tol})`);
    const k = `${s.size} ${s.look}`;
    const a = agg.get(k) ?? { exact: 0, near: 0, total: 0, maxDelta: 0, n: 0, minExactPct: 100 };
    a.exact += c.exact; a.near += c.near; a.total += c.total; a.maxDelta = Math.max(a.maxDelta, c.maxDelta); a.n++; a.minExactPct = Math.min(a.minExactPct, pct);
    agg.set(k, a);
  }
  console.log('# per-look parity (scenes = frames x sessions)\n# size look scenes exact% worst-scene-exact% maxDelta');
  for (const [k, a] of agg) console.log(`# ${k.padEnd(22)} ${String(a.n).padStart(3)} ${((100 * a.exact) / a.total).toFixed(3).padStart(8)} ${a.minExactPct.toFixed(3).padStart(8)} ${a.maxDelta}`);
  console.log(`# ${scenes.length} scenes, all >= 99.5 % exact, rest within one coverage level`);
  console.log(`# working 320x180 ${res.benchMsPerFrame!.toFixed(2)} ms/frame (draw+readPixels(1px), ${res.renderer}); informational, G3 belongs to P4`);
});

test('shader: static looks render identically at different t (GPU)', { skip: skipReason, timeout: 120_000 }, async () => {
  const mk = (step: number): SceneMeta[] => ['idle', 'review', 'needs-you', 'fault', 'unknown'].map(look => ({
    key: look, look, size: '320x180', hue: 200, step, w: 320, h: 180, cpu: new Uint8ClampedArray(0),
    u: uniformsFor({ look, hueDeg: 200, step, w: 320, h: 180 }),
  }));
  const a = await gpu(toIn(mk(0))), b = await gpu(toIn(mk(41)));
  assert.deepEqual(a.pixels, b.pixels);
});

test('shader: working frames actually move (a different step is a different image)', { skip: skipReason }, async () => {
  const mk = (step: number): SceneMeta[] => [{ key: 'w', look: 'working', size: '', hue: 200, step, w: 320, h: 180, cpu: new Uint8ClampedArray(0), u: uniformsFor({ look: 'working', hueDeg: 200, step, w: 320, h: 180 }) }];
  const a = await gpu(toIn(mk(3))), b = await gpu(toIn(mk(4)));
  assert.notEqual(a.pixels[0], b.pixels[0]);
});

test('parity test goes RED on a planted off-by-one lattice-row bug (detector self-check)', { skip: skipReason, timeout: 120_000 }, async () => {
  const needle = 'y - float(r) * RP';
  assert.ok(FIELD_FRAGMENT_SOURCE.includes(needle), 'planted-bug anchor moved: update this test');
  const planted = FIELD_FRAGMENT_SOURCE.replace(needle, 'y - float(r + 1) * RP');
  const scenes = buildScenes().filter(s => s.size === '320x180' && s.step <= 3 && s.hue === HUES[0] && ['idle', 'working', 'needs-you'].includes(s.look));
  const res = await gpu(toIn(scenes, planted));
  const worst = Math.min(...scenes.map((s, i) => (100 * compare(s.cpu, decode(res.pixels[i]), s.u).exact) / (s.w * s.h)));
  console.log(`# planted lattice bug: worst-scene exact ${worst.toFixed(3)} % (contract >= 99.5 %)`);
  assert.ok(worst < 99.5, `planted bug not detected: still ${worst} % exact`);
});
