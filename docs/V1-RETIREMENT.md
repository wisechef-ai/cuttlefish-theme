# V1 retirement ledger — cuttlefish-theme 2.0

The v1 terminal engine is gone from what ships (contract `test_structure.py::test_S5`).
This branch (`v2/python-half`) deletes it; `main` still has it (`0a33840` is the restore
point). The v2 rule that killed it: v1's live terminal repaint depended on core surfaces
that are forbidden or unmerged (skin-engine re-paint of a running app, the chrome
renderer) — v2 is desktop-first (SPEC C10) and the classic CLI keeps a STATIC skin only.

268 v1 tests were retired with the engine (`pytest --collect-only` on the twelve files
below, before deletion). Each file is mapped to the v2 contract test that now owns its
property, or marked a decommissioned surface.

## Test files

| v1 test file (tests) | what it pinned | v2 owner |
|---|---|---|
| `test_animator.py` (17) | transition cadence: idle costs nothing, a transition lands exactly on target | desktop loop discipline: `desktop/test/acceptance/oA_adapters.test.ts` (parked at rest, awake while working), `oA_part1_applied.test.ts` P3.4 (frames run and change the field while working, none at rest / reduced motion), `o4_motion.test.ts` (static states request no frames) |
| `test_field.py` (18) | the pixel grid: spatial correlation, layered compositing, single-band waves | the background field moved to the desktop domain: `desktop/test/acceptance/o2_language.test.ts` + `o2_part1_blanch.test.ts` (organs, ΔL band), the O7 pixel evidence (`tests/acceptance/test_o7_desktop_evidence.py`, `test_o7_part1_recompute.py`) |
| `test_mantle.py` (14) | multi-pigment mantle as the identity channel (never flat black) | hue = identity is the desktop `allocate()` (contract README domain API): "two sessions never share a hue" is pinned by `desktop/test/acceptance/o2_language.test.ts`; the visible surface: `oA_adapters.test.ts` (swatch per session row) |
| `test_morph.py` (23) | transition curves measured in the animal (Woo 2023): fast blanch, staggered recover, exact landing | decommissioned v1 surface, no v2 equivalent — v2 motion is one short bloom per state change (C3/C7), pinned as timing only (`BLOOM_MS`, `motionPlan`) in `desktop/test/acceptance/o2_config.test.ts` + `o4_motion.test.ts` |
| `test_seed.py` (2) | a session id seeds a stable identity through bootstrap | desktop `allocate(lineageRoot, peers)` determinism: `desktop/test/acceptance/o2_language.test.ts` (stable hues per root across the corpus) |
| `test_session.py` (23) | signal registry, reader robustness, liveness | the signal vocabulary is now data: `cuttlefish.settings` SIGNALS + the desktop reducer (`signalsOf`, `pollPlan`) pinned by `desktop/test/acceptance/o2_state.test.ts` + `o3_o5_desktop.test.ts`; validation of user input by `tests/acceptance/test_o5_live_config.py` (shared vectors) |
| `test_terminal.py` (28) | terminal colour promises: no theme-dependent indices, honest contrast, CVD collapse | decommissioned v1 surface, no v2 equivalent — the classic CLI is a static skin; the only colour promise left (identity is never core's amber/red, alarms keep their meaning) is `tests/acceptance/test_o6_cli_skin.py::test_O6_1_static_skin_shape` |
| `test_v6_acceptance.py` (15) | v6: mantle/skin acceptance on the terminal | superseded by the O2/O7 desktop pixel contract (see `test_field.py` row) |
| `test_v7_acceptance.py` (7) | v7: xterm-256 quantisation of the mantle | decommissioned v1 surface, no v2 equivalent — the desktop renders true colour; the classic CLI skin is static hex (`test_O6_1`) |
| `test_v8_acceptance.py` (10) | v8: the chrome renderer | decommissioned v1 surface, no v2 equivalent — the chrome renderer is an UNMERGED core hook; catalog rules forbid depending on it (`test_o1_catalog_clean.py::test_O1_4`) |
| `test_v9_acceptance.py` (6) | v9: transcript mantle acceptance | superseded by the desktop row-swatch contract (`oA_adapters.test.ts`: swatch per session, `data-cf-state`) |
| `test_v10_acceptance.py` (12) | v10: pigment classes (identity/acute sets, acute dominance) | state = pattern + brightness, never a hue change (C4): pinned by `desktop/test/acceptance/o2_language.test.ts` (classifier tells the five states apart on every identity and ground) + `o2_config.test.ts` (vectors); needs-you/error events reach the desktop via `tests/acceptance/test_o3_needs_you.py` + `test_o3_part1_approval_keys.py` |

## Proofs (`tests/proofs/`, 4 scripts, not pytest)

| proof | what it proved | v2 owner |
|---|---|---|
| `terminal_paint_proof.py` | a real `hermes` terminal PAINTS our colours (startup ordering) | the classic CLI skin is loaded by the REAL core skin loader: `test_o6_cli_skin.py::test_O6_3_the_real_core_skin_loader_accepts_it` |
| `live_repaint_proof.py` | rewriting the skin YAML repaints a RUNNING CLI | decommissioned v1 surface, no v2 equivalent — v2 never repaints the classic CLI (static skin, C10) |
| `animated_repaint_proof.py` | an animated transition reaches a live app frame by frame | the desktop budgeted loop carries the frames: `oA_part1_applied.test.ts` P3.4 + the O7 video evidence (`test_o7_desktop_evidence.py`, `test_o8_part1_video_provenance.py`) |
| `running_app_proof.py` | a repaint reaches a real running prompt_toolkit app | decommissioned v1 surface, no v2 equivalent — same reason as `live_repaint_proof.py` |

## Deleted engine surface

Root modules (`test_structure.py` `V1_ENGINE`, verbatim): `mantle.py chrome.py live.py
termbg.py field.py morph.py linework.py pattern.py patterns.py palette.py session.py
skinio.py banner.py bootstrap.py seed.py naming.py plugin.py cli.py` (`v19_adapter.py`
was already absent at this branch point). Directory: `color/`. The dirs `v19 python
packages gates design tui` were already absent. Kept: `conftest.py` and `pytest.ini`
(the acceptance contract still needs the hyphen-name import binding), `docs/` history,
`requirements-dev.txt`, `Makefile`.

## What replaced it (the v2 Python half)

`cuttlefish/` (events, hooks, settings, liveconfig, skin, cli, register),
`dashboard/plugin_api.py` + `dashboard/manifest.json`, `skins/cuttlefish.yaml`,
`plugin.yaml` v2.0.0. The desktop half (`desktop/`) is the other lane of the same
plugin.
