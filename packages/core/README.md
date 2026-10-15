# packages/core

The shared, host-free core of the cuttlefish theme (direction D "dots"). Hosts (the desktop plugin, the
TUI widget, the trace replayer) import it or consume its committed bundles.

## Layers (plan §13.3)

| dir | rule |
|---|---|
| `domain/` | pure. No I/O, no host imports, no `Date.now()` / `Math.random()`; clock and seed are injected. `tokens` (generated from `tokens.json`), `blake2b`, `identity`, `oklch`, `pattern`, `motion`, `state-hook`, `state-desktop`. |
| `ports/` | interfaces only: `Clock`, `EventSource`, `IdentityStore`, `Surface`. |
| `app/` | use-cases composing domain through ports. `resolve.ts`: `renderModel(...)`; `replay.ts`: `replay(traceLines, {stepS})`. |
| `tools/` | generators and fixture builders. Never imported by shipping code. |
| `fixtures/` | committed golden vectors (python-generated or python-cross-checked). |

`index.ts` is a flat export list. `CONTRACT.md` is the P2/P3 shared decision record (identity allocator,
reducers, trace format); the vault original wins if they differ.

## Test

```
cd packages/core && npm ci && npm test        # node --test; TypeScript runs natively (node >= 22.18), no tsc
node tools/gen-tokens.mjs --check             # domain/tokens.ts is generated from tokens.json
node tools/gen-identity-vectors.mjs --check   # needs python3; re-verifies every case against hashlib + a python reference
python3 tools/gen-blake2b-vectors.py --check  # every committed digest re-derived from hashlib
```

## Oracle rule

`design/directions/d-dots/direction.mjs` is the oracle for `domain/pattern.ts`. `test/pattern.oracle.test.ts`
requires byte-identical pixels and text for every P1 matrix scene (all three scales at the real host
surface sizes, six states plus degraded, working frames, the 20 fixture sessions, reduced motion, negative
and huge steps). If the look must change, change the oracle first, never the port alone. Known gaps left
for P4 (kept at parity on purpose): eyespot anti-aliasing and chip label coverage.

## Salvage (from `park/v20-desktop`, `apps/desktop/src/field/`)

- `identity.ts`: **ideas reused, algorithm rewritten.** Kept: blake2b seeding from the durable lineage id,
  farthest-point selection against live peers, reserved alarm arcs kept out of identity, "crowded is
  surfaced, never hidden", and golden-vector parity with the other language. Rewritten: v20 varied L and C
  over a free continuous space and imported `@noble/hashes`; direction D fixes L and C, so identity is a
  20-slot hue lattice (contract §1: a continuous farthest-point on 230 deg gives ~7.2 deg gaps at 20
  sessions, below the frozen G2 floor), and the hash is our own dependency-free BLAKE2b.
- `oklab.ts`: **not reused.** v20 carried a full gamut-mapping / deltaE pipeline; direction D needs only
  OKLCh to clipped sRGB, which `domain/oklch.ts` copies exactly from the P1 oracle.
- `mask.ts` (DOM transcript measurement) and `signal.ts` (session-dot to field-signal table): **not reused.**
  Both are host concerns (DOM) or are replaced by the state reducers (contract §2/§3, P2-STATE).

## State reducers and the replayer (contract §2, §3, §4)

- `domain/state-hook.ts`: TUI hook-bus reducer. `initial()`, `reduce(model, ev)`, `resolve(model, now)`, keyed by
  lineage root (`reduceKeyed`), plus the `since` tracker (`trackInit` / `trackStep`: time of the last change of the
  RESOLVED state). Constants `STALE_S = 20`, `REVIEW_DWELL_S = 0.6`.
- `domain/state-desktop.ts`: desktop reducer keyed by stored id; runtime ids with no mapping yet are buffered.
  `classifyParity(ours, coreLabel)` returns `match | allowed:<rule> | MISMATCH` against core's `SessionStatusDot`.
- `app/replay.ts`: `replay(lines, {stepS = 1})` gives, per lineage root (desktop: stored id), the identity and the
  resolved state at every event instant and at synthetic ticks every `stepS` (so stale -> unknown and the end of the
  review dwell are observed), then keeps ticking `TAIL_S` past the last event. Events that share an instant are applied
  together before one sample. Identity: per profile, first-seen order, `allocate()` against the slots already held by
  earlier roots of that profile, persisted per root (a later arrival never moves it; rotation keeps root and slot).
  `replayJson` / `canonicalJson` give stable-key JSON, so two runs (or two bundles) diff byte for byte.
- In `index.ts` the two reducers are exported with prefixes (`hookReduce`, `desktopReduce`, ...) because both modules
  name their functions `initial` / `reduce` / `resolve` after the contract.

## Bundles: how the hosts consume the core

`npm run build` (esbuild, version pinned in `package.json`) builds the SAME entry `index.ts` into two committed,
self-contained, import-free ESM files, deterministic (no timestamps, no absolute paths, no legal comments):

| file | platform / target | consumed by |
|---|---|---|
| `desktop/core.bundle.js` | browser, es2022 | P4 desktop plugin: **inline this file** into `plugin.js`. The desktop loader resolves only `@hermes/plugin-sdk/react`, so a bare `import` of the core cannot work there. |
| `tui/core.bundle.mjs` | node, node22 | P5 TUI widget: `import` it directly. |

Both carry the header `// GENERATED by packages/core/build.mjs from packages/core — do not edit`. CI job
`bundles-fresh` rebuilds and fails on any diff, so never hand-edit and never forget to rebuild after touching `domain/`,
`app/` or `index.ts`. `tools/traces/parity.mjs` replays every `tools/traces/*.jsonl` through both bundles and exits 1 if
they differ (2: `--require-all` and a state is never reached; 3: a desktop core-dot MISMATCH).
## Shader (XL field, `domain/field-shader.ts`)

One self-contained GLSL ES 3.00 fragment shader (plus a 3-line vertex shader), no library, no texture reads.
`uniformsFor({look, hueDeg, step, w, h})` precomputes every colour, the seed, the lattice and the frame step
from the domain, so the shader never derives OKLCh; `FIELD_UNIFORM_TYPES` is the name-to-binder table a host
uses. Paint at a low internal size (<= 57,600 px, e.g. 320x180) and let the compositor upscale with smoothing;
only `working` animates, every other look is one frame. The CPU pattern (`paint`, scale `XL`) is the oracle.

```
cd tools && npm ci && npx playwright install chromium     # once
cd packages/core && node --test "test/shader/*.test.ts"   # CF_REQUIRE_GPU=1 makes "no Chromium" a failure, not a skip
```

`test/shader/field-shader.parity.test.ts` renders every look (six states plus degraded) x 3 working frames x
4 sessions at 320x180 and at the P1 desktop XL size, reads the pixels back and requires >= 99.5 % exact with the
rest within one coverage level, per scene. It also proves static looks are identical at different times and goes
RED on a planted lattice-row bug. `BLANCH` / `GREY` are exported from `pattern.ts` so the two paths share them.

## Shader-salvage (from `park/v20-desktop`, `apps/desktop/src/field/`)

- `shaderHarness.ts` `fieldProgram` / `acquireGl` / `renderShaderFrame`: **idea reused, rewritten.** Kept: compile
  and link once per context, a fullscreen triangle-strip, `readPixels` on a `preserveDrawingBuffer` context,
  never faking pixels when WebGL2 is missing. Rewritten as `test/shader/gl-harness.ts` `renderScenes`: it runs
  inside Chromium via Playwright, binds uniforms from a type table, flips readPixels to top-down, and benches.
- `shader.ts` `FIELD_VERTEX_SOURCE`: **reused** (same `aPos` pass-through), now in `domain/field-shader.ts`.
- `shader.ts` `hash2` + `toU`: **rewritten.** v20 hashed with `0x45d9f3b` imul and a float to uint bridge; D's
  `hash(i, j, k)` is `Math.imul` + `>>>` on int32, so the GLSL uses `uint` arithmetic directly and needs no bridge.
  The lesson kept: never seed in float32 (a 24-bit mantissa cannot carry a 32-bit seed).
- `shader.ts` `vnoise`: **reused** (smoothstep value noise, same corner blend) for the `review` mottle.
- `shader.ts` `fractal5`, `contractionAt`, `uMaskBoxes`, `uMaskCount`, `uSignal`, `uTime`: **dropped.** The v20 look
  (fractal field, transcript contraction mask, signal tint) is superseded by D; D animates by a frame step only.
- `shader.ts` `cbrtF`, `oklabFromLinear`, `linearFromOklab`, `oklchToLinear`: **dropped.** Colours are precomputed
  by `uniformsFor` through `oklch.ts`, which is byte-equal to the oracle; the shader does no colour maths.
- `shader.ts` ES 1.00 twin (`FIELD_FRAGMENT_SOURCE_ES1`, `FIELD_VERTEX_SOURCE_ES1`): **dropped.** Chromium and
  Electron give real WebGL2 (SwiftShader in CI), so the software-GL stand-in is gone.
- `shader.test.ts` parity shape (bounded LSB + exact %): **kept, tightened.** v20 allowed max 4 LSB and > 90 %
  exact on a 96x64 frame and skipped silently without a context; D requires >= 99.5 % exact and the rest within
  one coverage level per scene, and CI fails if the GPU tests did not run.
- `render.ts` `renderFieldToRGBA` (v20 CPU oracle): **dropped.** The oracle is now `pattern.ts` `paint`, itself
  byte-identical to the P1 `d-dots/direction.mjs`.
