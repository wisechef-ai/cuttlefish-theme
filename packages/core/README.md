# packages/core

The shared, host-free core of the cuttlefish theme (direction D "dots"). Hosts (the desktop plugin, the
TUI widget, the trace replayer) import it or consume its committed bundles.

## Layers (plan §13.3)

| dir | rule |
|---|---|
| `domain/` | pure. No I/O, no host imports, no `Date.now()` / `Math.random()`; clock and seed are injected. `tokens` (generated from `tokens.json`), `blake2b`, `identity`, `oklch`, `pattern`, `motion`. |
| `ports/` | interfaces only: `Clock`, `EventSource`, `IdentityStore`, `Surface`. |
| `app/` | use-cases composing domain through ports. `resolve.ts`: `renderModel(...)`. |
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
