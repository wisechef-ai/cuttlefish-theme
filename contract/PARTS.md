# Contract PARTS (index) — closes the holes luna found in the locked contract `c0c06eb`

Parts are NEW files. No file of the locked contract was modified (`git diff --diff-filter=MDRTUXB c0c06eb -- contract tests/acceptance desktop/test/acceptance`
is empty; the only differences are the added files below). Same rules as the locked contract: builders make them green without editing them.
A wrong part is fixed by the lead in its own commit. Branch `v2/parts`.

| part file | closes | what it adds | RED at `c0c06eb`, and why | commit |
|---|---|---|---|---|
| `tests/acceptance/test_o3_part1_approval_keys.py` | F1 | The request-key derivation rule for approval-only pairs (producer `request_id` else stable key over `(session_key, turn_id, tool_call_id, pattern_key, surface)`); elicitation pair; coalesced follower; gateway wrapper + inner pair → 0 open | 15 errors: `ModuleNotFoundError: No module named 'cuttlefish_theme.cuttlefish'` (the product package does not exist) | `8e4ba05` |
| `desktop/test/acceptance/o2_part1_blanch.test.ts` | F2 (pale half), F5 (O2.10) | error organs' mean OKLab L ≥ same session's resting + 0.01, chroma ≤ 0.03, ΔL ≥ 0.012; EVERY circle of `toSvg` matches a distinct dot | 4 fail / 1 pass: `desktop/src/domain/index.ts did not load: ERR_MODULE_NOT_FOUND`. The 1 pass (P2.5) proves the comparison itself rejects dropped/recoloured/moved circles | `f2bebe7` |
| `desktop/test/acceptance/oA_part1_applied.test.ts` (+ `fake/part1_probe.mjs`) | F3, F5 (loop draw) | comment-stripped, parsed CSS: `[data-chat-surface]` rule with a decoded SVG data-URI of ≥ 40 circles; no `background`/`background-color`; composer-ring VALUES differ resting → needs you and return; strip words differ across 4 presets; frames run and change the field while working, none at rest / reduced motion | 5 fail / 1 pass: `Cannot find module desktop/plugin.js`. The 1 pass (P3.0) is the CSS instrument's own test (comments ignored, inert rules seen as inert) | `3d24be7` |
| `desktop/test/acceptance/oA_part2_added_state.test.ts` | F8 | A user-added state (`compacting_seen`, custom pattern) reaches swatch `data-cf-state`, strip label, `html[data-cf-state]`; priority and relabel apply live; its pattern is the one drawn; rejected additions change nothing; removal returns to resting | 5 fail: `Cannot find module desktop/plugin.js` | `d9c0756` |
| `tests/acceptance/test_o7_part1_recompute.py` (+ `instruments_py.py`, `raw_evidence.py`, `test_instruments_py.py`, `test_raw_evidence.py`, `contract/RAW-EVIDENCE.md`) | F4, F5 (idle floor), F9 (composer/strip) | Every manifest number recomputed from raw DOM dumps / PNG stills / CPU CSVs / vision response; sha256-bound; idle still has ≥ 20 organs | 12 errors: `evidence/v2/manifest.json missing`; R13–R15 (loader rejections) pass | `dbbb111`, hardened `5e544ae`, `001895b` |
| `tests/acceptance/test_o8_part1_video_provenance.py` | F9 (video, compare URL) | `kit/video/cut.json` (segments add up to ffprobe ±0.5 s, ≥ 4 states, ≥ 4 sessions, bound to the O7 capture sha, legend opener ⊂ [0,10] s) and `kit/PR-COMPARE-URL.txt` | 2 fail: `…/kit/video/cut.json missing`, `…/kit/PR-COMPARE-URL.txt missing`; 4 validator tests pass | `2b6f8f8` |

Nothing for F7, m10, m11, F2's hue half (refuted). F6: see below.

## F6 scope note (O1.4 / O1.5)
The text scans of `test_o1_catalog_clean.py` guard against **accidental dependence on forbidden doors** and are not an anti-obfuscation lint. O1.3
parses Python with `ast`; for the Desktop plugin the fake host (`desktop/test/acceptance/fake/`) throws by name on any SDK door, DOM query, bare timer,
`requestAnimationFrame`, `localStorage` or `MutationObserver` it does not model, so adapter tests catch evasion at runtime on every exercised path. A
deliberate obfuscation by our own builder is a review finding (sonnet per work package, sol at M5), not a lint target.

## Collection and runs (cwd = this worktree, `TMPDIR=/tmp`)
- `pytest tests/acceptance -q --collect-only` → **218 tests collected**, no collection error (147 before the parts).
- `pytest tests/acceptance -q` → 106 passed, 66 failed, 45 errors, 1 skipped (the failures/errors are the locked and new product-dependent tests, RED for missing product).
- `node --test desktop/test/acceptance/*.test.ts` → runs every file (107 tests; 13 pass: the instrument tests and the parts' self-tests; 94 fail for the missing product).
- `ruff check tests/acceptance` → clean (the repo's `ruff.toml`, mccabe 9).
- Part self-tests that are GREEN without any product: `test_instruments_py.py` (57), `test_raw_evidence.py` (42), the O7 loader tests R13–R15, the O8 validator tests V3–V5, P2.5, P3.0.

## AIMED: GREEN on a prototype that satisfies it, RED on a prototype with exactly the defect (all in `~/.hermes/cache/scratch/cf2-parts-proto/`, never in the repo)
| part | GREEN prototype | RED prototypes (defect → failing tests) |
|---|---|---|
| F1 | `cuttlefish/{events,hooks}.py`: producer id else sha256 over the five fields; coalesced calls emit nothing → 15/15 | random per-call key → 12 fail; coalesced post closes the leader → P1.8 fails |
| F2 | domain stub: error organs achromatic, lighter than resting (dark grounds) / between resting and ground (light ground) → P2.1–P2.5 green and the locked O2.2/O2.3/O2.4 stay green | dark achromatic error → P2.1, P2.2 fail (margin −0.079 on `#141416`); `toSvg` that only draws the first 50 circles faithfully → P2.4 fails |
| F3, F8 | scratch `plugin.js` under the locked fake host → 11/11 (P3.0–P3.5, P4.1–P4.5) | tokens only inside a CSS comment → P3.1, P3.2, P3.4, P3.5 fail; constant strip text → P3.3 + 1 more; constant ring → P3.2 + 1 more; frozen field → P3.4; label not surfaced → P4.1, P4.2; additions ignored → P4.1–P4.3, P4.5; `html[data-cf-state]` stuck on presets → P4.1 |
| F4/F5/F9 (O7) | `gen_evidence.py` writes a consistent `evidence/v2` (5 stills 1200×800, 5 DOM dumps + idle window, 4 CPU CSVs + field CSV, vision text) → 15/15; the locked O7 also passes on it | each single defect turns exactly the intended test red: manifest lies about pixels → R7; blank idle still → R9; CPU number lie → R10; tampered dump → R1; DOM state lie → R3; same composer colour → R6; vision omits a still hash → R12; cropped region → R7–R9 error |
| F9 (O8) | `kit/` with an ffmpeg 69.5 s video + generated `cut.json` + URL → 5/5 | cut missing 3 segments + compare branch `main` → 2 fail (states/sessions < 4, branch) |
| instrument port | pinned to Ottosson 2020, Wikipedia percentile, constructed fields; 3 random-dot cross-checks against `instruments.ts` through node (1e-9) | — |

### Measured pale band (the lead prototype for F2, before the lock)
Prototype: 60 organs/field, resting mean ΔL ≈ 0.028 (p95 ≤ 0.04), error grey pigment. Per ground, min over the 20 roots:
`#141416` margin L(err) − L(rest) = 0.0186 (need ≥ 0.01; slack 0.0086), error mean ΔL ≥ 0.0466; `#2e3440` the same; `#fbfbfa` margin 0.0131 (slack 0.0031), error mean ΔL ≥ 0.0149.
Permitted band for the error organs' mean ΔL: dark grounds `[resting + 0.010 … 0.2)`, light ground `[0.012 … resting − 0.010]` = `[0.012, 0.018]` for this resting. **The light-ground band is narrow (0.006)**: it widens only if resting is
louder (resting mean up to ≈ 0.035 under the locked p95 ≤ 0.05 gives `[0.012, 0.025]`). Satisfiable, not roomy: the builder should tune error brightness per ground, not set one constant.

## IMPLEMENTABLE: TypeScript signature check
Scratch copy of the tree in `…/cf2-parts-proto/ts` with a type-only stub of every symbol `contract/README.md` lists for `desktop/src/domain/index.ts`
(`export declare …`, no bodies), `typescript@5` + `@types/node@22` installed in that scratch dir only:
`node node_modules/typescript/bin/tsc --noEmit -p .` (`allowImportingTsExtensions`, `moduleResolution: bundler`, `strict`, include `desktop/**/*.ts`) → **exit 0** over the locked JS contract files and the three JS parts. A deliberate
type error in `o2_part1_blanch.test.ts` made the same command exit 2 (negative control). Scratch copy deleted afterwards.

## Engineering evidence on the new code (tools in `~/.local/bin`, run on copies of the files in a scratch dir so no `.metrics/` lands in the repo)
- Complexity (`crapper --no-coverage`): after refactors every changed function ≤ 9 (`read_png`, `load_cpu_csv`, `region_ok`, `_opener_problems`, `step` = 9; first pass flagged `cut_problems` 14, `load_still_meta` 12, `detect_organs` 10, `matchBrace` 12, `splitDeclarations` 11, `boot` 10, `tick` 10 — all split). CRAP needs a coverage run the tool cannot do for these test-tree files: reported as N/A.
- Duplicates (`dryer --threshold 0.8`): none.
- Mutation (`mutator`, one file at a time, test files cannot be mutated in place, so run on a scratch project that imports copies; `PYTHONDONTWRITEBYTECODE=1` after discovering stale `.pyc` produced false survivors):
  - `raw_evidence.py`: 124/124 killed.
  - `instruments_py.py`: 308/312 killed; survivors `58 <= → <` (threshold 0.04045 is never an integer/255), `73 +360 → −360` (`% 360` makes it identical), `215 <= → <` (a trailing 8-byte chunk header can only be IEND, ignored either way), `228 <= → <` (Paeth `pa == pb` with `a ≠ b` forces `pc == 0`, so the winner is `c` either way; the whole predictor is also compared against an independent reference over 0..13³).
  - `test_o8` validators: 57/59; survivors `> → >=` on the 0.01 and 0.05 tolerances (the boundary is not representable in floats).
  - `part1_probe.mjs` CSS helpers: 37/40; survivors `46 < → <=` (indexOf at `length` is −1), `74 head[1] → head[0]` (both contain `;base64`), `80 ?? → ||` (match returns null or an array).
  - `LoopDriver`/`boot`/`textOf` and the three Python part files' assertions are exercised through the prototypes above, not mutated.
- Rejection tests per new input: PNG (bad signature, 16-bit, interlaced, bad compression/filter method, truncated, short data, zero size), CSV (header, unparsable, negative/NaN, backwards time, empty), DOM dump (every field, schema, state, sha, rows), still sidecar (schema, state, sha, region/exclude shape), vision (missing/duplicate verdict, no model line), region rules, cut.json and compare URL (each a unit case). Run-twice safety: the parts are read-only on the repo and the evidence; they write nothing but pytest's own tmp files.

## OPEN
- `finished_unseen` pixels are not measured (it never shows in the focused field; a swatch-crop measurement is not pinned). Classifier thresholds on real pixels are pinned only for resting and needs_you (as in the locked O7.5).
- The GitHub user in the compare URL is unconstrained beyond the URL grammar (the fork owner is Adam's account; not stated in the brief).
- The stills used for measurement must show an empty transcript outside `exclude` rectangles (≤ 25 % of the region): a harness-side obligation, documented in `RAW-EVIDENCE.md`.

## Findings against the locked contract (reported, nothing touched)
- `Makefile` `RELEASE_ONLY` lists only the two locked release tests; `test_o7_part1_recompute.py` and `test_o8_part1_video_provenance.py` need evidence/kit and will fail `make contract-py` until the harness ran. The lead should add them to `RELEASE_ONLY` (the Makefile is outside the locked paths).
- The literal "no diff under `contract/`, `tests/acceptance/`, `desktop/test/acceptance/`" check lists the ADDED part files; the meaningful form is `--diff-filter=MDRTUXB` (no existing file changed), which prints nothing.
