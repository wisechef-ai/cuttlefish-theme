# Review — lane `adapters` (glm-5.3) at `7a1bdda`, reviewer: claude-sonnet-5-5

## Scope / diff
`git diff --stat 37f5d33..7a1bdda`: 22 files, +4042, all under the owned paths (`desktop/src/adapters/**`, `desktop/src/index.ts`,
`desktop/build.mjs`, `desktop/plugin.js`, `desktop/test/unit/adapters/**`). No deleted tests/tools/docs, no domain/Python/README edits.
No scope creep found. `git diff --exit-code 5358f8c -- contract tests/acceptance desktop/test/acceptance` → rc 0 (empty).

## Gates re-run by me (builder's numbers confirmed, none inflated)
| gate | result | wall |
|---|---|---|
| `node --test desktop/test/acceptance/*.test.ts` | rc 0, 116 pass / 0 fail (per file: instruments 11, o2_config 42, o2_language 10, o2_part1_blanch 5, o2_state 8, o3_o5 4, o4_motion 6, oA_adapters 10, part1 7, part2 5, part3 2, part4 4, part5 2) | 6.8 s |
| `node --test desktop/test/unit/*.test.ts desktop/test/unit/adapters/*.test.ts` | rc 0, 126 pass / 0 fail | 5.1 s |
| `CF_STRICT=1 make contract-py` | rc 0, 198 passed | 34 s |
| `make lint` | rc 0 (ruff, compileall, `node --check`, `tsc --noEmit` — desktop/node_modules present, so tsc really ran) | — |
| `node desktop/build.mjs --check` | rc 0 (100449 bytes) | — |
| `make test` (lint + unit + contract-js + contract-py) | rc 0 | 69 s |

## RED-proofs (scratch copy `/tmp/rp`, production line broken, restored)
| claim | break | tests that failed |
|---|---|---|
| loop parked at rest / under reduced / off | `wantsFrame` → `return true` | A5, A7 + 4 unit (loop, runtime) |
| dispose leaves no loop | `teardown` skips `loop.dispose()` | A5, A9, unit runtime dispose |
| polling only while Python half off | `pollWanted: () => true` | A6 |
| swatch hue = identity only | seed swatch hue with `sessionId+state` | P6.2, P6.3, P6.4 |
| **ring ("composer ring") = identity hue, never state** | `ringOf(hue + (working?40:0))` | **NOTHING FAILED** (30 acceptance + 45 adapter unit pass) → F5 |

## The fake host vs the real v0.22.7 SDK (read-only: the pinned core checkout's `apps/desktop/src`)
Verified OK against the real source:
- `PluginContext.onEvent/setTimeout/setInterval/register/rest/onDispose` — `contrib/plugin.ts:119-154,336-396`; scoped, disposed with the plugin. `GatewayEvent` is `{type, session_id, payload}`, fanned to `'*'` (`contrib/events.ts:55`). Plugin events arrive via `_broadcast_global_event` → `session_id: ""` (server.py:587,632) — `eventToFeed` maps that to `session:null`, payload carries the stored id, as README pins.
- `host.state.{busyBySession,busy,focusedSessionId,focusedStoredSessionId,activeSessionId,gateway,viewport}` are nanostores atoms (`sdk/index.ts:556-604`) with `get/listen`. `busyBySession` is keyed by RUNTIME id and is built from ALL session states (index.ts:225); `busy` is the FOCUSED chat only (index.ts:566).
- `createBudgetedLoop` (`lib/budgeted-loop.ts`): draw gets a rAF timestamp, `idleWhen` is checked only after a draw, `wake()` is a no-op unless dormant; paused while hidden. The adapter's use is correct.
- `config.get {key:'mtime'}` is a real getter (`tui_gateway/methods_config.py:249,283`). `ctx.rest('/config'|'/health')` → `/api/plugins/<id>/…` (`api/plugins.ts:73`).
- `SESSION_ROW_AREAS` render contract: `contribution.data.render({sessionId})`, `sessionId` is the STORED id (`lib/session-row-slots.ts:25`); mounted as a component. `titleBar.center` stays mounted on every route (`app/contrib/controller.tsx:522`). `COMPOSER_AREAS.top`, `STATUSBAR_AREAS.right` exist.
- Bundle: only the three allowed specifiers; I ran the real loader's `importSpecifierRe` over `desktop/plugin.js` — only the three real imports are in code (one regex hit is inside a string). No eval/fetch/XHR/WebSocket/rAF/localStorage/querySelector/MutationObserver.

Gaps between fake and real (the findings):

## Findings
| id | sev | where | evidence |
|---|---|---|---|
| F1 | MAJOR | `runtime.ts:40-46` `sampleGround`, `ground.ts` | Reads the CUSTOM PROPERTY `--ui-chat-surface-background` via `getPropertyValue`. A custom property is returned as its *authored token stream*; in v0.22.7 it is `var(--ui-bg-chrome)` and `--ui-bg-chrome` is `color-mix(…)` (`styles.css:297,399`). `parseGround` only understands `#rrggbb`/`rgb()` → `null` → the plugin ALWAYS paints on the dark fallback `#141416`, on every theme. The fake returns `rgb(…)` for `getPropertyValue`, hiding it. Light themes get dark-ground dots (violates C7 near-invisible). Fix: resolve through a probe's `backgroundColor` (the engine resolves color-mix) and parse `rgb()`/`rgba()`/`color(srgb …)`. |
| F2 | MAJOR | `feedmap.ts:60` | Deviation "omit an EMPTY busyBySession map" is **right in intent, wrong in effect, and not a domain defect.** I probed the domain: `map{a:true}` then `map{}` ⇒ `a` idle (a present map, even empty, correctly means "nobody busy"). The adapter omission means that when the host's map goes `{a:true}` → `{}` (state entry dropped) the busy set is never replaced ⇒ a session shows "working" forever. The fake never links `busy` and the map, which is why the builder saw a "silenced flag"; in the real host `busy` ⊂ map. Fix: omit the empty map only while the plain `busy` flag is true (the fake-only combination); send `{}` when `busy` is false. |
| F3 | MAJOR | `runtime.ts:121-131,95-99` | Nothing wakes the loop when the live reduced-motion switch goes OFF→on-again, or a refetched config flips `motion` back from `off`, while the focused session is still working: `wireReduce`/`applyConfig` only repaint; `wake()` happens only via `armBloom` (state change). Clouds stay dead until the next state change. The builder's own unit test works around it by forcing a new state. |
| F4 | MAJOR | `surfaces.ts:50-60` (`stateChip`, rim) | Binding design #2: rim = thin band, 4–6 px tall, full width. Shipped rim = the 64×12 strip SVG plus the label text (same chip as the status bar), i.e. a text banner in `composer.top`. Not reported as a deviation. |
| F5 | MAJOR (test gap) | `painter.ts:39`, tests | A mutant making the composer ring colour depend on the state survives the whole contract + unit suite (RED-proof table). The builder's "96/96 sites killed" is false for this line; the C4 "state never changes a hue" guard on `--dt-composer-ring` only holds for `needs_you` in the locked test. |
| F6 | MINOR | `surfaces.ts:68-72` | `TitleMount` subscribes to the view and runs `useEffect` with no deps: under real React the owned `<style>` is removed and re-created on every version bump (each feed event/viewport change) — churn + needless re-decode of a ~23 KB data URI. The fake ignores deps and never re-renders, so it is invisible there. |
| F7 | MINOR | `runtime.ts:166-169` | Live viewport listener applies width/height 0 raw (the 0→1200×800 fallback exists only at attach). |
| F8 | MINOR (open) | `runtime.ts` | Ground is sampled once at attach; a later theme switch leaves a stale ground until reload. No MutationObserver allowed; a periodic re-sample is a design choice → left open. |
| F9 | INFO | bundle | 100 449 B, ~70 KB of it the whole domain (no tree-shaking; unused exports ship). One-time parse of ~100 KB is negligible (loaded once per window); not worth a bundler. Per-frame cost is bounded: `fieldCss` ≈ 23 KB / ≈ 2.5 ms at 1200×800 and unchanged at 7680×4320 (organ count is capped by the domain). |

## Lie hunt (the rest)
- Self-comparing / existence-only tests: none found in the adapter unit tests (they compare against the domain oracle or exact CSS text).
- Flattening to hold a ceiling: none (field is 23 KB of real organs; rim/strip render real dots).
- Domain impurity: untouched by this lane; `desktop/src/domain` has no SDK/DOM/clock/random imports (S3 passes).
- Motion under off/reduced: parked correctly (A5, M2 RED-proof) — except the resume bug F3.
- Dead modules: none; every adapter module is imported by `runtime.ts`/`surfaces.ts`.
- Duplicates: `dryer --threshold 0.8` run in the fix round (below).

---
# Fix round (same branch)

| id | status | fix | failing-first test (RED at `7a1bdda` on behaviour) | mutant (old line restored → test fails) |
|---|---|---|---|---|
| F1 | fixed | `runtime.ts` `sampleGround` resolves via a probe's `background-color: var(--ui-chat-surface-background)`; `ground.ts` parses `rgb()`/`rgba()`/space `rgb(r g b / a)`/`color(srgb …)`, rejects translucent | `runtime: the ground is what the engine RESOLVES…`, `feedmap: parseGround understands…`, `…percentage alpha…` | `getPropertyValue` back → runtime test fails |
| F2 | fixed | `feedmap.ts` forwards the authoritative empty map unless the flag is true (flag-only sources) | `feedmap: a present-but-emptied busyBySession map clears…` (+ corrected the old test that pinned the bug) | `Object.keys(...)>0` only → 2 tests fail |
| F3 | fixed | `runtime.ts` `paint()` ends with `wakeIfWanted` (reduce, config, feed, viewport) | `leaving reduced motion while working wakes…`, `a refetched config that re-enables motion wakes…` | remove call → both fail |
| F4 | fixed | `svg.ts` `bandElement` (pattern tile scaled uniformly 5/12, full width), `surfaces.ts` `RimView` 5 px, no words; strip keeps its look | `surfaces: the composer rim is a 4–6 px full-width band…`, `svg: the band tiles the WHOLE strip…` | height 12 / width 64px → test fails |
| F5 | fixed (test) | no prod bug; new test pins the ring across working/needs_you/error | `runtime: the composer ring is the identity hue in EVERY state` — fails against the F5 mutant | ring + 30° in error → test fails (it survived 30 acceptance + 45 unit before) |
| F6 | fixed | `TitleMount`: no `useLive`, `useEffect(…, [mountStyle])` (stable fn) | no test: the fake ignores effect deps and never re-renders — behaviour is real-React-only; covered by the A4/oA suites staying green | — |
| F7 | fixed | live viewport goes through the same 0 → window-size fallback | `runtime: a live viewport of 0 keeps…` | raw `applyEnv(v, vp)` → fails |
| F8 | fixed (conductor ruling) | `runtime.ts` `resampleGround` runs from a new optional `onTick` hook on the EXISTING mtime tick in `configwatch.ts` (no new timer/observer/rAF); re-renders only when the sampled ground changed; a throwing hook never costs the config sighting | `runtime: the ground is re-sampled on the config tick…` (RED at `1aec8ab`: field stayed on the dark ground; asserts rendered field + rim, 0 writes and parked loop when unchanged), `configwatch: a throwing onTick…` | `if (false) return` → fails; hook removed → fails |
| F9 | info | bundle 103 028 B; whole domain ships (~70 KB TS source); acceptable | — | — |

Plus the conductor's asks:
- Dispose/hot-reload: `runtime: dispose leaves no style, attribute, timer, listener, loop or live contribution; a second life never doubles` (passes at `7a1bdda` too — it is a proof, not a fix): after dispose, 0 owned styles, 0 root attributes, 0 live timers, 0 event listeners, 0 matchMedia listeners, 0 listeners on every `host.state` atom, 0 live contributions, every loop disposed; two consecutive lives each have exactly one loop and one style.
- busyBySession deviation: judged **adapter bug, not a domain defect** (domain correct: present map replaces, empty map = nobody busy; probe in F2). No `contract_findings`.
- Bundle: only the three specifiers; see F9.

## Gates after the fixes
`make test` (lint + tsc + unit + contract-js + contract-py): rc 0 — 116 acceptance, 198 Python; unit (domain + adapters) 137 pass / 0 fail; `build.mjs --check` rc 0 (103 028 B);
contract-unchanged diff vs `5358f8c` empty. crapper: max CC 9 (`stateSnapshot`, < 10); dryer `--threshold 0.8`: no duplicates;
mutator (one file at a time, `--no-coverage`, unit + oA acceptance as the test command): ground 11/11, feedmap 22/22, svg 9/9, runtime 17/17, surfaces 7/7 killed.
