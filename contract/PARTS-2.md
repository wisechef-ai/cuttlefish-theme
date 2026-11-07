# Contract PARTS-2 — fixes for the luna review of the PARTs (ruling R-P2)

`PARTS.md` and every part-1 file are locked at `9bfb49f` and untouched. Each fix is a NEW file; `git diff 9bfb49f -- contract tests/acceptance desktop/test/acceptance` lists additions only.
Release-evidence parts (need the real-Desktop evidence or the kit; the conductor adds them to the Makefile `RELEASE_ONLY`):
**`tests/acceptance/test_o7_part2_bindings.py`** and **`tests/acceptance/test_o8_part2_frames.py`**.

| part file | closes | what it pins | RED at `9bfb49f` | aimed |
|---|---|---|---|---|
| `tests/acceptance/test_o3_part2_pairing.py` | L1, L2 | multiset per derived key (0→1 true, 1→0 false, empty fields hash as "", stray close emits nothing); one human approval counts once: per `session_key` a `human_input(approval)` and a non-coalesced approval hook pair up oldest-first, `true` on the first-opened, `false` when both closed; coalesced follower = alias; two humans never pair; clarify never pairs. Events AND open count asserted after every step, for the gateway, transport and elicitation producer orders | 12 errors: `No module named 'cuttlefish_theme.cuttlefish'` | reference hooks → 12/12 (and part 1 15/15); no multiset → P2.1; no pairing → P2.5/6/8/9/10; coalesced emits → P2.10 |
| `desktop/test/acceptance/oA_part4_added_state_oracle.test.ts` | L3 | swatch of the added state carries its name and its circles equal `renderSwatch` (domain oracle, same resolved settings + seed `SA`, `allocate(seed, [])` hue, ground `#141416`) as canonical circles; label from the oracle; live pattern edit redraws as the oracle | 4 fail: domain index.ts / plugin.js missing | oracle-sharing scratch plugin → green; swatch always draws the default pattern → P6.2, P6.4 (and part 2's P4.3) |
| `desktop/test/acceptance/oA_part5_property_allowlist.test.ts` | L4 | every declaration of the owned style: on `[data-chat-surface]` only `--*`, `background`, `background-image/-position/-size/-repeat`; on `:root`/`html`/`html[data-cf-…]` only `--*`; negative controls `visibility color opacity display filter transform content mix-blend-mode` (+ `background-color`, `z-index`, `position`, `pointer-events`), also inside `@media` and in selector lists | 1 fail / 1 pass (P7.0 checker self-test): plugin.js missing | good plugin → green; `opacity:.99` on the surface or `color:red` on `:root` → P7.1 |
| `tests/acceptance/raw_evidence2.py` (helper, beside the locked `raw_evidence.py`) + `tests/acceptance/test_o7_part2_bindings.py` | L5, L6, M1, M2 | below | 4 errors `manifest.json missing`; 8 negative-control tests pass | consistent evidence → 12/12; each defect below turns the intended test red |
| `tests/acceptance/test_o8_part2_frames.py` | L8 | below | F1: `cut.json missing`; 5 synthetic-video controls pass | scratch kit from a synthetic capture → F1 green; one segment declaring the wrong source time → PSNR 11 dB, red |

## Schema additions (O7)
`manifest.raw.cpu_windows[idle_on|idle_off|working_on|working_off] = {file, dom_dump, roles: {pid: renderer|gpu|main}}`, `manifest.raw.cpu_order` (names in measured order),
`manifest.capture.stills[i].dom_dump` for every measured still (one with `meta`), and `raw/dom/win.<name>.json` (`cf2-window-dump/1`: `{schema, window, plugin: on|off, captured_at, html, rows[{swatch_circles}]}`).
- L5: the window dump was captured inside its CPU window; `on` shows `html[data-cf-state]` and ≥ 1 swatch; `off` shows no `data-cf-*` and no swatch; all four windows sample the same pid ROLES (renderer, gpu, optional main); windows do not overlap; `cpu_order` equals the timestamp order. Controls: the on dump labelled `off` (`twoon`), mismatched roles, wrong order, overlap, capture outside the window.
- L6: `exclude` rects have positive size and lie inside the still (`[[0,0,1200,400],[0,0,1200,-400]]` is rejected); each measured still's dump has `transcript_messages == 0`.
- M1: every manifest path (`raw.files`, `raw.cpu*`, sessions, stills, vision, windows) resolves under `evidence/v2/raw/`: no absolute path, no `..`, no symlink out, no other `evidence/` subtree.
- M2: a manifest still's `state` equals its sidecar's; a measured state appears once.
- Aimed defects on synthetic evidence: `escape` → B1 (+B4), `mislabel` and `dupstate` → B2, `negrect` and `transcript` → B3, `twoon`, `roles`, `order` → B4.

## Schema additions (O8 frames)
`cut.json` segment 0 (the legend card) gains `card_png` (path relative to `kit/video/`) and `card_png_sha256`. With ffmpeg: the demo frame at every capture segment's output midpoint equals the capture frame at `in + (mid − start)`, and the demo frames at t = 1, 5, 9 s equal the card PNG, all PSNR ≥ 30 dB at 640 px wide (so the card is still shown at 9 s). Controls (synthetic `testsrc2` capture, built per run in a tmp dir, never committed): a repeated still, a wrong-time cut labelled with the declared time, a different card, a wrong card hash, a size mismatch.

## Deferred / refused
L7 is deferred to the conductor's measured probe (W1): nothing written. Part 1 files untouched (including the locked `README.md` prose on `--composer-ring-strength`).

## Gates re-run
Collection of the whole suite, `node --test desktop/test/acceptance/*.test.ts`, ruff, the type-only-stub `tsc --noEmit` and the contract diff: see the lane report.
