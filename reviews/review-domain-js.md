# Review: v2/domain-js (builder glm-5.3, head 4d7433d) — reviewer claude-sonnet-5-5

Judged against contract lock `5358f8c` (merged into the branch as 8687bc4).

## Diff
`git diff --stat c0c06eb..4d7433d`: 25 files, +2479, all under the owned paths
(desktop/src/domain/**, desktop/test/unit/**, desktop/package.json, package-lock.json, tsconfig.json).
Nothing deleted, nothing outside the lane, no contract/test edits. The unit tests import the locked
`../acceptance/{corpus,instruments,language}.ts` read-only (fine).
Contract diff: `git diff --exit-code 5358f8c -- contract tests/acceptance desktop/test/acceptance` -> exit 0, empty.

## Gates (run by me, TMPDIR=/tmp, nice -n 10)
| gate | result |
|---|---|
| acceptance JS, per file: instruments 11/11, o2_config 42/42, o2_language 10/10, o2_part1_blanch 5/5, o2_state 8/8, o3_o5_desktop 4/4, o4_motion 6/6 | all exit 0 (whole set ~10 s wall) |
| unit `node --test desktop/test/unit/*.test.ts` | 76/76, exit 0 |
| pytest S1/S2 | 2 passed |
| `tsc --noEmit -p .` strict | exit 0 (but `--noUnusedLocals` reports 5 dead items: see M3) |
| crapper desktop/src/domain | 115 fns, max CC 9 (builder's number reproduced) |
| dryer --threshold 0.8 | no duplicate candidates |
| whole JS contract `desktop/test/acceptance/*.test.ts` | the 7 lane files green; oA_* (adapters/bundle, 24 tests) red = next lane |
| whole `pytest tests/acceptance` | 65 failed / 124 passed / 61 errors: all in Python/adapters/evidence files (o1,o3,o5,o6,o7,o8, structure S3+) = other lanes; S1/S2 pass |

## RED-proofs (scratch copy in /tmp/scratch, never the branch)
- `BLANCH_LIGHTER_LIGHT 0.012 -> 0`: P2.1, P2.2 fail (pale is load-bearing).
- `failed` not sticky (`'error' ? false`): O2s.2 fails.
- bloom ignores `off`: acceptance o4 still PASSES (6/6) but 2 unit tests fail -> the unit pins are what protect it.
- blanch/spot pigment hue +40 deg: spot is caught by a golden digest; **blanch hue +40 survives all 76 unit + all acceptance tests** (F4).

## Specific asks
1. Pale margin (mean OKLab L error - resting, min over 20 roots): #141416 0.0148 (max 0.0173), #2e3440 0.0148,
   #fbfbfa **0.0107** (max 0.0132). MIN 0.0107; headroom to the 0.01 contract bound is 0.0007 on the light ground
   (margin itself is not < 0.002 of anything it is measured against, but the *headroom* is thin). Error mean dL on light
   0.0136 vs floor 0.012 (headroom 0.0016). Swept 12 other grounds (#000..#fff, solarized, sepia): flat 0.0148 (dark) / 0.0111
   (light), no ground fails. The margins are constants (BLANCH_LIGHTER_*), independent of hue and root.
2. Hue = identity: max OKLab-hue deviation of any organ from the slot hue over 20 roots x 3 grounds x 5 presets = 3.3 deg
   (sRGB gamut rounding), never a state function. Organs never move: positions identical in 8100 configurations
   (20 roots x 3 grounds x 5 presets x 3 t x 3 sinceChange x 3 motions). OK. (But see F4: no test pins hue per state.)
3. Purity: grep for Date|performance|Math.random|setTimeout|document|window|globalThis|process|require under
   desktop/src/domain: none. Imports are intra-domain only. OK.
4. Ledger: 29 justified. Judged equivalent: digestOf i<=8 (OOB typed write discarded), feed `??`->`||` family, `learn()`
   re-validation family, num `<=`, settings `??`->`||` / dead sentinel / fatal-dropped fallbacks, smallCloudInk max(1,..).
   blake2b `lo < vl[a]` -> `<=` (3 sites): equivalent only unless the *working-state* word vl[b]/vl[d] is exactly 0
   (probability 2^-32 per op); the ledger's stated reason ("4 aligned zero bytes inside a hashed string") is wrong
   (padding words are zero routinely and those are the *killed* sites at lines 35/45). Accept as probabilistic
   equivalent (F9, MINOR, doc only).
5. renderField best-of-5 (process.cpuUsage, load avg ~10): 1200x800 1.25-1.30 ms, 2560x1440 1.32 ms. < 5 ms. OK.
   Caches are bounded (constellation 64, plan 256); organ count is fixed (~190) regardless of surface size.
6. Traces: o2_state 8/8; failed sticky until next message.start (R3 RED-proof); offline never busy, busy only from host
   busy state (signalsOf SIGNAL_RULES: `c.open && ...`). OK.

## Findings
| id | sev | where | evidence |
|---|---|---|---|
| F1 | MAJOR | pattern.ts:176 `twinkleFactor` / field.ts:43 | `reducedMotion` is never consulted by the twinkle: with motion `alive` + `reducedMotion:true`, `renderField` at tMs=0 vs 3000 differs (probe prints `true`). C3 "honours prefers-reduced-motion" is only honoured by the loop plan, not the render. |
| F2 | MAJOR | feed.ts:26 `REDUCERS[input.kind]`, `own()` | `reduceFeed(m,{kind:'__proto__'})` throws TypeError; `kind:'toString'` returns the *string* "[object Undefined]" as the model; `'hasOwnProperty'`/`'valueOf'` throw. `own()`/`session()` read inherited props for ids like `toString` -> needs_you with session_id `toString` throws; `session:'hasOwnProperty'` throws. Header claims "garbage input is ignored, never thrown". |
| F3 | MAJOR | settings.ts `v in patterns`, `STATES[name]` | a state whose `pattern` is `"toString"`/`"constructor"`/`"hasOwnProperty"` is accepted with NO warning; `patternOf` then throws at render time (user-editable config file, live reload). A state named `toString` is treated as a preset (STATES inherited lookup). |
| F4 | MAJOR | pattern.ts:68 | the error (blanch) pigment's hue is not pinned by any test: mutating it to hueDeg+40 passes all suites. "hue = identity, never a state" is a headline spec rule; the code is right, the guard is missing. |
| F5 | MINOR | pattern.ts:10,31,52 / field.ts:41 / pattern.ts:138; `RenderCore.dots` always `[]`; `cloudDl` `small` branch dead | dead imports/constants/params (tsc --noUnusedLocals: 5). |
| F6 | MINOR | motion.ts:21 | bloom envelope is discontinuous at T_PEAK (0.918 -> 1.0 step, 0.25 s): a visible tick on the fast open. |
| F7 | MINOR | pattern.ts:55 | error organs on light grounds are *fainter* (dL 0.0136) than resting (0.0268): contract-allowed, but "blanching" there is near-invisible; headroom 0.0016 to the 0.012 floor. |
| F8 | MINOR | feed.ts `pollPlan` | `void nowMs`: parameter required by contract, intentionally unused (no cadence state). Documented, not a lie. |
| F9 | MINOR | MUTATION-LEDGER.md | wrong reason for the blanket blake2b carry equivalence (see ask 4). |
