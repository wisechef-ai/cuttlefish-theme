# Review: python-half (glm-5.3) — `v2/python-half` @ e07b5580, base 5358f8c

Reviewer: claude-sonnet-5-5. Every number below was produced by this reviewer, not quoted.

## Diff
`git diff --stat 5358f8c..e07b558`: 68 files, +1876/−9560. Adds `cuttlefish/**` (cli, events, hooks, liveconfig, pairing, register, settings, skin),
`dashboard/{manifest.json,plugin_api.py}`, `skins/cuttlefish.yaml`, `plugin.yaml`/`__init__.py` rewrite, `tests/unit/**` (9 files),
`docs/V1-RETIREMENT.md`; deletes the v1 root modules, `color/`, `tests/test_*.py`, `tests/proofs/`, `tools/{README,record_demo_gif,render_*,sample_photos}`.
All of it is inside the lane's owned paths plus addendum 2's tools/proofs. No scope creep found; no contract file touched; `tools/desktop/` absent as ordered.

## Contract unchanged
`git diff --exit-code 5358f8c -- contract tests/acceptance desktop/test/acceptance` → rc 0, empty (before and after my fixes).

## Gates (reviewer-run)
| gate | result |
|---|---|
| O3 x3 (needs_you, part1, part2) + O5 + O6 | 85 passed, 0 failed, 2.3 s |
| O1 `-k "O1_2 or O1_3 or O1_4"` | 3 passed; S5 1 passed |
| `tests/unit` at e07b558 | 68 passed (84 after fixes) |
| `make lint PY=…` | rc 0, "All checks passed! / lint ok" |
| WHOLE python contract `pytest tests/acceptance` (196 s, split not needed) | 212 passed, 11 failed, 27 errors, 1 skipped — all failures are other lanes: O1.5 (bundle), S1–S4 (desktop domain), S6 (docs), O7*/O8* (release-only evidence/kit). Nothing in the python half's surface. |
| `node --test desktop/test/acceptance/*.test.ts` (3 s) | fails `ERR_MODULE_NOT_FOUND desktop/plugin.js` — desktop lane absent, expected |

## RED-proofs (scratch copy `/tmp/rvscratch/cf`, branch untouched)
1. pairing `and`→`or` on "both closed": `test_P2_5_gateway_order…counts_once` fails.
2. drop the `coalesced` guard in `_fire_approval`: `test_P1_6_a_coalesced_follower…` fails.
3. add command text to the derived key: `test_P1_3_derivation_is_stable…ignores_text` fails.
Also one mutant per fix below (all killed).

## Hunt list
- self-compare / existence-only tests: none found in the unit files read (pairing, hooks, settings assert emitted sequences).
- thresholds met by flattening, hue/organ motion, motion under off: not applicable to the Python half (no rendering).
- impurity in `desktop/src/domain`, per-frame cost: not this lane.
- dead modules/no-ops: none; every cuttlefish module is reachable from `register.py`/`plugin_api.py`.
- duplicates: `dryer --threshold 0.8 cuttlefish dashboard` → "No duplicate candidates found."
- producer ORDERS replayed against hermes-core v0.22.7 sources: gateway (human open → pre → post → human resolved) counts once; transport the same; MCP elicitation (pre/post, no wrapper) counts alone; coalesced follower (pre and post both carry `coalesced=True`) emits nothing; two concurrent approvals count 2. Correct.
- `requires_hermes ">=0.22.0"`: all four files are added in v0.22.0 (`git tag --contains` lists v0.22.0 as the lowest 0.22 tag for each of d109785b, 585e296d, 8034d493, 72f55062) → floor is truthful.
- skin install: one file (`skins/cuttlefish.yaml`, temp+`os.replace`), never edits config.yaml, never selects the skin. OK.

## Mutation (every survivor accounted)
`mutator --no-coverage --mutate-all --test-command "<unit + the lane's acceptance>"`: pairing 16/16, hooks 14/14 (after fix), liveconfig 8/8,
settings 35/37 → 2 survivors at `settings.py:262` (`section[:-1]` → only the wording of a warning message). Killed by new test R4 (now 37/37 expected; see commit).
Note: crapper reports 0 % coverage in this environment (no coverage report wired); CC worst = 8 (`read_raw_settings`), all < 10.

## Findings
- **F1 MAJOR** `cuttlefish/hooks.py` (`_text(kwargs,"kind") or "approval"`, was line ~90/103): the producer's `kind` string was echoed verbatim into the
  broadcast payload. Brief: never broadcast prompt/command/error TEXT. Evidence: `on_human_input_request(kind="SECRET-TOKEN-xyz")` → payload `"kind": "SECRET-TOKEN-xyz"`.
  FIXED: allowlist `approval|clarify|sudo`, anything else → `"other"`.
- **F2 MAJOR** `cuttlefish/settings.py` `_number` (line ~71): `math.isfinite(10**400)` raises `OverflowError`, so a config with a huge integer crashes `resolve_settings`
  ("never raises"), `/config` and `hermes cuttlefish doctor`. FIXED: `isfinite` only for floats; ints compare exactly.
- **F3 MAJOR** `cuttlefish/liveconfig.py` `read_raw_settings`: a non-UTF-8 `config.yaml` raised `UnicodeDecodeError`, and a deeply nested one `RecursionError`
  (neither is `OSError`/`YAMLError`) → `/config` 500 on every poll. Brief ask 4 ("never crashes on bad YAML"). FIXED: both degrade to defaults + one `config` warning.
- **F4 MINOR (open)** `pairing.py`: a pair whose member shares its derived key with a second, unpaired hook open emits `active:false` when the pair closes although the
  second is still open (L1 multiset violated in the pairing+collision corner). Needs identical-key non-coalesced hooks in one session; not reachable from the
  producers' normal flows. Probe: human h1 open, hook K open (pairs), hook K open again, close hook K + h1 → `false` emitted with one still open.
- **F5 MINOR (open)** `pairing.py` TTL: after the 24 h drop, a late genuine close finds nothing and emits nothing, so the desktop's `active:true` is never cleared by
  the plugin (desktop must expire it). Design choice ("pruning never emits"), consistent with the brief's bound.
- **F6 MINOR (open)** `request_id`/`session_key` are echoed as given (identifiers by the producers' contract, not text); a hostile producer could still put text there. Not changed.
- Builder's report discrepancies: none material. Its claim 15/15 hooks mutants vs my 14 after the fix is a site-count difference (the `_text(…) or` expression was replaced by `_kind`).

## Verdict
Three MAJORs found and fixed with behaviour tests that fail at e07b558 (`tests/unit/test_review_fixes.py`, 9 RED of 15 on first run; the other 6 are positive controls and rejection inputs that already held).
No BLOCKER. Three MINORs open.
