# Acceptance contract: Cuttlefish 2.0 "desktop-first"

Locked. Builders make it green WITHOUT editing any file under `contract/`, `desktop/test/acceptance/` or
`tests/acceptance/`. A wrong contract is fixed by the lead (cf-lead) in its own commit, never by a builder.
Spec: `SPEC.md` §Cuttlefish C1–C10 (vault `projects/hermes-hackathon-2611/`). Plan: `cuttlefish/PLAN.md`.

## Run
```
make contract          # everything below, in order; exit code is the verdict
make contract-js       # node --test desktop/test/acceptance/*.test.ts
make contract-py       # .venv/bin/pytest tests/acceptance -q
```
Tests that need a real Hermes (`hermes plugins validate`) read `HERMES_BIN` (default `~/.local/bin/hermes`) and
always run with a throwaway `HERMES_HOME`. With `CF_STRICT=1` (set by `make contract`) a missing Hermes is a FAILURE,
never a skip.

## The words
- **lineage root / stored id**: the durable session id the sidebar row slot hands a plugin. **runtime id**: the id
  gateway events carry.
- **signal**: a detectable condition: `idle busy tool needs_input failed unseen compacting subagents offline`.
- **state**: a named entry of `settings.states`, chosen by signal + priority. **Presets**: `resting working
  needs_you error finished_unseen`.
- **pattern kind**: `mottle clouds zebra blanch eyespot`. A **pattern** = `{base: kind, density, contrast, scale}`.
- **ΔL**: |OKLab L(dot composited on the ground) − L(ground)|, measured by `desktop/test/acceptance/instruments.ts`.

## API the domain must export (`desktop/src/domain/index.ts`; pure: no SDK, DOM, clock, randomness)
```ts
type Motion = 'still' | 'alive' | 'off'
type Signal = 'idle'|'busy'|'tool'|'needs_input'|'failed'|'unseen'|'compacting'|'subagents'|'offline'
type PatternKind = 'mottle'|'clouds'|'zebra'|'blanch'|'eyespot'
interface PatternSpec { base: PatternKind; density: number; contrast: number; scale: number }
interface StateSpec { when: Signal; pattern: string; priority: number; label: string }
interface Settings { intensity: number; motion: Motion; states: Record<string, StateSpec>; patterns: Record<string, PatternSpec> }
interface Warning { code: string; path: string; message: string }
interface Dot { x: number; y: number; r: number; color: string /* #rrggbb */; alpha: number; role: 'organ'|'eyespot' }

const DEFAULT_SETTINGS: Settings
function resolveSettings(raw: unknown): { settings: Settings; warnings: Warning[] }
function stateFor(settings: Settings, signals: ReadonlySet<Signal>): string
function patternOf(settings: Settings, state: string): PatternSpec

function allocate(lineageRoot: string, peers: readonly number[]): { slot: number; hue_deg: number; crowded: boolean }

interface FieldInput {
  seed: string; width: number; height: number; hueDeg: number; ground: string /* #rrggbb */
  pattern: PatternSpec; intensity: number; motion: Motion; reducedMotion: boolean
  tMs: number; sinceChangeMs: number
}
function renderField(input: FieldInput): Dot[]                       // the background field (XL)
interface SwatchInput { seed: string; hueDeg: number; ground: string; pattern: PatternSpec; intensity: number }
function renderSwatch(input: SwatchInput): { dots: Dot[]; width: number; height: number }   // row swatch (S)
function renderStrip(input: SwatchInput): { dots: Dot[]; width: number; height: number }    // status strip (M)
function toSvg(dots: readonly Dot[], width: number, height: number): string

function motionPlan(i: { motion: Motion; reducedMotion: boolean; pattern: PatternKind; sinceChangeMs: number }):
  { animate: boolean; fps: number }
const BLOOM_MS: number

interface FeedInput { kind: string; t: number; session?: string | null; payload?: Record<string, unknown> | null }
function initialFeed(): FeedModel
function reduceFeed(model: FeedModel, input: FeedInput): FeedModel
function signalsOf(model: FeedModel, storedId: string): Set<Signal>
function knownSessions(model: FeedModel): string[]                  // stored ids, sorted
function pollPlan(model: FeedModel, nowMs: number): { pollActiveList: boolean; intervalMs: number }
function configPlan(model: ConfigWatch, mtime: number | string | null): { refetch: boolean; next: ConfigWatch }
function initialConfigWatch(): ConfigWatch
```

### Feed inputs (`kind`)
| kind | from | payload / session |
|---|---|---|
| `state` | `host.state` snapshot | session = runtime id or null; `{gateway, busy?, stored_session_id?, busyBySession?, focused_session_id?, focused_stored_session_id?}` (the recorded traces carry one line per runtime id with `busy`; a live adapter may send the whole `busyBySession` map, which REPLACES the per-runtime busy set) |
| `session.info` | `host.onEvent` | session = runtime id, `{stored_session_id}` |
| `message.start` / `message.complete` | `host.onEvent` | session = runtime id; complete carries `{status: 'complete'|'error'|'interrupted'}` |
| `tool.start` / `tool.complete` | `host.onEvent` | session = runtime id |
| `status.update` | `host.onEvent` | session = runtime id, `{kind}` (`compacting` → signal) |
| `subagent.start` / `subagent.complete` | `host.onEvent` | session = runtime id |
| `plugin.cuttlefish-theme.needs_you` | Python half | `{session_id /*stored*/, session_key, request_id, kind, active: bool}` |
| `plugin.cuttlefish-theme.error` | Python half | `{session_id /*stored*/, session_key, retryable: false}` |
| `python.health` | `ctx.rest('/health')` result | `{ok: bool}` |
| `active_list` | `session.active_list` poll | `{sessions: [{id /*runtime*/, session_key /*stored*/, status}]}` |

Semantics pinned by the tests: **busy** comes only from host busy state (per-runtime `busy` or a `busyBySession` map);
`message.start` alone never makes a session busy (a killed backend leaves a start with no complete). While the gateway is
not `open` a session carries `offline` and never `busy`. `failed` is sticky until the next `message.start` of that session.
`unseen` = a turn completed (`status: complete`) while another session was focused; focusing clears it. A needs-you
request is cleared by its own resolve (`active: false`, same `request_id`) or by the session's `message.complete`.

### Python half (`cuttlefish/`)
```python
cuttlefish.settings.resolve_settings(raw) -> tuple[dict, list[dict]]   # same vectors as the JS (contract/config-vectors.json)
cuttlefish.events.EVENT_PREFIX == "plugin.cuttlefish-theme."
cuttlefish.hooks.{pre_approval_request, post_approval_response, on_human_input_request,
                  on_human_input_resolved, api_request_error}(**kwargs) -> None   # never raise
cuttlefish.events.set_broadcaster(fn | None)   # test seam; default = hermes_cli.plugin_events.broadcast_plugin_event, imported lazily
dashboard/plugin_api.py: router with GET /config -> {settings, warnings, rev}; GET /health -> {ok: true, version}
cuttlefish.skin.install(hermes_home) / uninstall(hermes_home)   # the static classic-CLI skin, explicit command only
```

### Adapters (asserted by `desktop/test/acceptance/oA_adapters.test.ts` against the SHIPPED `desktop/plugin.js`)
- Default export `{ id: 'cuttlefish-theme', name, register }`; one self-contained ESM file importing only
  `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`; first line `// GENERATED …` (built by `desktop/build.mjs`, whose
  `--check` mode exits non-zero when the committed file differs from a fresh build).
- One `SESSION_ROW_AREAS` contribution whose `data.render({sessionId})` NEVER returns null for a real id; the swatch root
  element carries `data-cf-session=<id>` and `data-cf-state=<state name>` and draws an SVG.
- At least one `STATUSBAR_AREAS` item naming the focused state's `label` in words; at least one `TITLEBAR_AREAS`
  permanent mount that owns exactly ONE `<style>` (field on `[data-chat-surface]` as an `data:image/svg+xml` layer;
  composer ring through `--dt-composer-ring` / `--composer-ring-strength`; no `background-color`; no
  `data-slot|testid|sidebar|tour`), plus `html[data-cf-state]` for the focused session. Dispose removes all of it.
- Exactly one `createBudgetedLoop` (fps ≤ 10, `idleWhen` declared): parked at rest, awake while the focused session
  works, parked under `prefers-reduced-motion` (live) and under `motion: off` (live, from config).
- Polling only through `ctx.setInterval` (≥ 2 s; `session.active_list` 3–10 s apart and only while the Python half is
  off/unknown). Settings: `config.get {key:'mtime'}` → `ctx.rest('/config')` on change, applied in place.
- Never `host.sessions.setColor`, `requestTheme` or `setAccentOverride`: the user owns colours and theme.
- The fake host (`desktop/test/acceptance/fake/`) models only these doors; any other SDK function, any DOM query into
  the app, bare timers, `requestAnimationFrame`, `localStorage` and `MutationObserver` throw by name.

### Field geometry the classifier reads (`desktop/test/acceptance/language.ts`)
Clouds (working) and zebra stripes (needs you) lie along one of the four canonical orientations (0/45/90/135°).
Thresholds were proven jointly satisfiable before the lock (lead prototype, 0/600 misreads; margins: clouds lowK
0.88–0.95 vs ≥ 0.55; resting lowK ≤ 0.32; zebra highK 0.97–1.10 vs ≥ 0.60; resting highK ≤ 0.34).
