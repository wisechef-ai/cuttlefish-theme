# Mutation ledger — desktop/src/domain

Every mutator site (792) is either killed by the suite in this directory plus the six
locked acceptance files, or justified here as an equivalence over the inputs the domain
can receive. Accounting: 583 killed by unit/acceptance coverage filters, 108 on first
full-suite adjudication, 30 by the round-2 pins, 36 by the round-3 pins, 6 by the round-4
dial digests, 29 justified below. 763 + 29 = 792.

The kill-tests live in `mutation-pins.test.ts`; each round of them exists because a
survivor exposed a behaviour no earlier test could distinguish from a near-miss.

## Justified survivors (29)

### blake2b.ts — 4

- `G` carry ternaries `lo < vl[a]` -> `lo <= vl[a]` (the three/four `v[x] + v[y]` sites, not the
  `+ message word` sites, which ARE killed because zero padding words occur routinely): they
  differ only when the working-state word added (`vl[b]` / `vl[d]`) is exactly 0 mod 2^32.
  Those words are pseudo-random mixing state, so this is a probabilistic equivalent (~2^-32 per
  operation), not a structural one; every digest the domain produces is pinned byte-exact (RFC 7693
  vectors, the seededStream pin, golden render digests) and the mutants match them all.
  (Corrected in review: the earlier text blamed zero bytes in the hashed string.)
- `digestOf` `i < 8` -> `i <= 8`: the ninth iteration writes past the end of the 64-byte
  Uint8Array; out-of-bounds typed-array writes are discarded by spec. Identical output.

### feed.ts — 9

- `reduceSubagent` `own(m.subRt, rt) ?? 0` -> `||`: stored value is a nonnegative count;
  the only falsy defined value is 0 and `0 ?? 0` = `0 || 0`.
- `reduceSessionInfo`, `reduceState` (x2) `&&` -> `||` guarding `learn()`: learn()
  re-validates both ids and returns the model unchanged on junk.
- `applyStored` `length > 0` -> `>=`: at length 0 the mutant returns a fresh [] where the
  original returns the same empty array — value-equal; the domain never mutates in place.
- `applyRuntime`, `reduceTool` `?? []` -> `||`: stored value is an array (truthy, even empty).
- `focus` `?? null` -> `||`: storedOf values are nonempty strings.
- `reduceActiveList` `isRec(e) && idOk(e.session_key)` -> `||` feeding `seen.add`: the
  extra keys are non-strings or DANGEROUS strings; stored ids are always idOk strings, so
  the added keys can never match the only consumer, `seen.has(stored)`.

### field.ts — 1

- `num` `< 1e-4` -> `<=`: at |v| exactly 1e-4 the original's `toFixed(3)` = "0.000" is
  reduced to "0" by the trailing-zero strip on the next line — both branches emit '0'.

### pattern.ts — 1

- `smallCloudInk` `Math.max(1, n / 6)` -> `Math.max(0, n / 6)`: small-constellation organ
  counts are seed-independent (the skip test reads un-jittered lattice positions): the
  swatch always has exactly 14 organs, the strip exactly 18. For n in {14, 18}, n/6 > 1,
  so both maxes equal n/6.

### settings.ts — 14

- `stateFor` `-Infinity` -> `Infinity`: dead sentinel — `best === null` short-circuits the
  first comparison, so bestPriority is always written before it is read.
- `stateFor` `name < best` -> `<=`: differs only when name === best; Object.keys yields
  each name once.
- `stateFor` `best ?? 'resting'` -> `||`: best is null-or-nonempty-name.
- `readWhen` (x2), `readPatternRef` (x2) `?? fallback` -> `||`: def is
  undefined-or-nonempty-string.
- `readPriority` `def ?? Number.NaN` -> `||`: for def = 0 (resting preset) the mutant's
  NaN fallback is caught by the `Number.isNaN(n)` branch, which returns
  `{ value: def ?? 0 = 0, fatal: isNew }` — the value the original produced directly.
- `readPriority` `def ?? 0` -> `def ?? 1` (x3): the fallback fires only for NEW states,
  whose draft is fatal and dropped whole — the value is never observable.
- `readPriority` `def ?? 0` -> `||` (x3): the only falsy defined def is 0, and
  `0 ?? 0` = `0 || 0`.

## What the kill-rounds exposed

Round 2: the sfc32 stream was only tested for determinism/range (not exact draws); the
buffer cap was never hit at exactly 64; status-junk gates; junk-key purity; the needs_you
lifecycle; inclusive range endpoints; preset defaults surviving partial overrides;
alphabetical tie-breaks; motionPlan boundaries; hueDistance symmetry; the first golden
field digest.

Round 3: the needs_you signal alone cannot tell WHICH request survived (the record had to
be pinned); focus semantics for bare snapshots, runtime-id resolution and dangerous ids;
active_list must create no session from a dangerous-id entry; toSvg's predicate needed
synthetic dots at its boundary (r = 0.5, r = 0, alpha = 0); effectiveDl needed non-unit
dials; zebra needed scale != 1; small-canvas ink had never been pinned.

Round 4: every earlier digest ran with density = contrast = scale = 1, where `*` and `/`
agree — two digests with the dials off unity close that.
