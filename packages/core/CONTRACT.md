---
tags: [project, cuttlefish, sprint, contract]
type: lead-decision
codename: cuttlefish_2909
created: 2026-10-15
author: Builder (P2-LEAD t_4ea6a976)
binds: [P2 core (TS), P3 python half, P4 desktop, P5 TUI]
---

# P2/P3 shared contract — identity allocator, state reducer, trace format

> **Revision cf2909.contract/3 (D2-CORE-STATE, 2026-10-21):** `working` is split into `thinking | tool` (7 states). §2/§3 below are
> amended in place; the hook→state table is §2.1. Bus entries are `cf2909.bus/2`; a `/1` entry saying `working` reads as `thinking`.

P2 (TS core) and P3 (Python half) run in parallel. These are the decisions both must implement
**identically**; the P23 reviewer checks parity over 10k random cases and every recorded trace.
Decided by the P2 lead so the two halves never decide the same question twice. Precedence: plan §0/§8/§13 >
this file. Change only by a logged lead decision (LOG.md) — never unilaterally in one half.

The repo copy lives at `packages/core/CONTRACT.md` (P2-CORE commits it verbatim); this vault file is the
original and wins if they ever differ before P2 merges.

## 1. Identity allocator (direction D)

Direction D fixes lightness and chroma (tokens.json: dot L 0.58/0.66/0.74, C 0.135). **Identity is a hue
slot only.** The v20 allocator (park/v20-desktop `field/identity.ts`, which also varied L and C over a free
continuous space) is NOT salvaged as an algorithm: continuous farthest-point on a 230° arc gives gaps of
230/32 ≈ 7.2° at 20 sessions → rendered ΔE_OK ≈ 0.017 < the frozen G2 floor 0.020. A 20-slot lattice is the
spacing P1 proved on rendered pixels (G2 0.0228 @16/@20). Salvaged from v20: blake2b seeding, farthest-point
selection against live peers, alarm-arc exclusion, "crowded is surfaced, never hidden", vector-file parity.

Constants:

```
ARC_START = 110.0          # degrees, inclusive  (tokens.identity.hue_arc_deg)
ARC_END   = 340.0          # exclusive
SLOTS     = 20
STEP      = (ARC_END - ARC_START) / SLOTS          # 11.5
hue(k)    = ARC_START + STEP * (k + 0.5)           # k in 0..19 → 115.75 … 334.25 (exact in binary64; identical to tools/p1/stub-sessions.json hues)
CAP       = 3              # slots; spacing beyond this is "far enough"
```

`preferred(lineage_root: str) -> int`:
`d = blake2b(utf8(lineage_root), digest_size=32)`; `preferred = int.from_bytes(d[0:8], 'big') % SLOTS`.
(Python: `hashlib.blake2b(s.encode('utf-8'), digest_size=32)`. TS: a pure, dependency-free BLAKE2b in
`packages/core/domain/` — the desktop renderer has no `node:crypto` — tested against hashlib vectors;
use BigInt or two 32-bit halves for the mod, never a float.)

`allocate(lineage_root: str, peers: list[int]) -> {slot, hue_deg, crowded}` where `peers` = slots already held
by OTHER live sessions of the same profile (duplicates allowed, order irrelevant):

```
if lineage_root is empty/whitespace → error (caller degrades to 'unbound', never guesses)
pref = preferred(lineage_root)
if peers is empty: return slot=pref, crowded=false
free = [k for k in 0..19 if k not in peers]
if free is empty: return slot=pref, crowded=true            # >20 live peers: hue repeats, label carries identity
score(k) = ( min(CAP, min(|k - p| for p in peers)),  -|k - pref|,  -k )
slot = argmax over free of score (lexicographic)            # far enough first, then closest to the hash, then lowest index
return slot, hue(slot), crowded = (min distance to peers of slot) < 1   # i.e. never true when free is non-empty
```

Rules: allocation is **persisted by lineage root** (P3 `identity.json`) — once allocated, a session keeps its
slot even if peers change (§13.4 #4: order-/cache-independent ⇒ the persisted value is the identity; the
algorithm only runs for a lineage root with no record). The TS fallback (registry unreachable) runs the SAME
function with `peers=[]` (plan §1.4 "same hash without peer spacing"), or with the peer slots it can see.
`hue_deg` is reported rounded to 2 decimals in JSON. Lineage root = walk `state.db sessions.parent_session_id`
to the root (spike 05/06); the reducer never walks — callers pass it.

Golden vectors: `packages/core/fixtures/identity-vectors.json` (P2-CORE generates ≥ 2,000 cases from the TS
implementation AND checks each digest against Python `hashlib`; P3's `identity.py` test must load and match it).
Case shape: `{"lineage_root": str, "peers": [int], "slot": int, "hue_deg": float, "crowded": bool, "preferred": int}`.

## 2. State reducer (hook vocabulary — TUI bus; spike 06)

Pure: `reduce(model, event) -> model`, `resolve(model, now) -> state`. No clock reads; `now` is passed.
States: `idle thinking tool review needs-you fault unknown` (7; `working` is retired — D2-CORE-STATE; + `degraded` is a *rendering* of unknown with no binding,
not a reducer state). Model per lineage root:

```
in_turn: bool          tools: set[str]          pending: set[str]  fault: bool        review_until: float|None
finalized: bool        last_seen: float          bound: bool        pid_alive: bool|None
```

| event (`kind`) | effect |
|---|---|
| `on_session_reset` | model := fresh (in_turn F, tools ∅, pending ∅, fault F, review None, finalized F) |
| `on_session_start` | no state effect (late: first turn only) |
| `pre_llm_call` | in_turn T; tools ∅; fault F; finalized F |
| `post_llm_call` | tools ∅; fault F |
| `on_session_end` (any `completed`) | in_turn F; tools ∅; pending ∅; if `completed is True`: fault F |
| `on_session_finalize` | finalized T; in_turn F; tools ∅; pending ∅ |
| `pre_tool_call` with `tool_name=='clarify'` | pending += `clarify:<tool_call_id>` |
| `post_tool_call` with `tool_name=='clarify'` | pending -= `clarify:<tool_call_id>` |
| `pre_tool_call` with any other tool | tools += `tool:<tool_call_id>` |
| `post_tool_call` with any other tool | tools -= `tool:<tool_call_id>` |
| `pre_approval_request` | pending += `approval:<tool_call_id or session_key+'/'+pattern_key>` |
| `post_approval_response` | pending -= the same key |
| `api_request_error` | if `payload.retryable is true`: no change (transient, provider is retrying; proof of life only). Otherwise (false/absent/non-bool): fault T (sticky; no turn-end follows an error) |
| `pre_verify` | review_until := t + 0.6 (min dwell; pure observer, returns None) |
| `heartbeat` | (bus/liveness) last_seen := t; pid_alive := T (a heartbeat is written only by a live owner) |
| `pid_dead` | pid_alive F (stays F until a later `heartbeat` or `on_session_reset`; other hooks do NOT revive it) |
| `binding` `{bound: bool}` | bound := value |

Every event from the session also sets `last_seen := t`.

`resolve(model, now)`, first match wins:
1. `unknown` if `finalized` or `pid_alive is False` or `bound is False` or `now - last_seen > STALE_S` (STALE_S = 20.0; the bus heartbeats every 5 s while the owner lives)
2. `needs-you` if pending non-empty
3. `fault` if fault
4. `tool` if in_turn and tools non-empty; else `thinking` if in_turn
5. `review` if review_until is not None and now < review_until
6. `idle`

("turn ended" is never needs-you; stale is never the last known state; `tool` never outlives the `post_tool_call` of its last open call, and every turn boundary closes open tools.)

### 2.1 Hook → state table (cf2909.contract/3)

| hook | resulting state (if nothing higher in the precedence holds) |
|---|---|
| `pre_llm_call` (`on_stream_*` is not subscribed: it is only proof of life) | `thinking` |
| `pre_tool_call` (tool ≠ clarify) | `tool` |
| `post_tool_call` (last open tool closed) | `thinking` |
| `pre_tool_call` clarify, `pre_approval_request` (`on_human_input_request` is not a core hook in this runtime) | `needs-you` |
| `api_request_error{retryable:false}` (or flag absent) | `fault`, sticky until the next `pre_llm_call` |
| `api_request_error{retryable:true}` | no change (stays `thinking`/`tool`; the recorded retryable trace never faults) |
| `on_session_end{completed}` | `idle` |
| `pre_verify` outside a turn | `review` (0.6 s dwell) |

### 2.2 Capability flag `tool_signal`

Each host declares whether its event stream tells a tool from the model thinking: `TOOL_SIGNAL = {tui: true, desktop: true}`
(`packages/core/domain/state-hook.ts`, `python/domain/resolve.py`). A host with `false` maps busy → `thinking` only. Python writes it to
`<HERMES_HOME>/cuttlefish/hooks.json` (`cf2909.hooks/2`) and `hermes cuttlefish doctor` prints it. Verified, not assumed: TUI from the hook
vocabulary (spike 06); desktop from the spike-07 receipt (`tool.start` / `tool.complete` reach `host.onEvent('*')` with the runtime id)
and from the three recorded desktop traces, which carry them (desktop-main 3, desktop-kill 5). Python `bus.py` writes the resolved
state + `since` (time of the last change of the resolved value); TS replays the same events.

## 3. State reducer (desktop vocabulary — spike 07)

Keyed by **stored** id. The host speaks **runtime** ids; the runtime → stored mapping is learned from (a) `session.info.payload.stored_session_id`,
(b) the host's live focused pair on a state snapshot (`focused_session_id` + `focused_stored_session_id` = `host.state.focusedSessionId` /
`focusedStoredSessionId`, same instant as the busy flip), and (c) a `stored_session_id` on a state line that was KNOWN at that snapshot (the converter
never looks ahead). Other events (`message.*`) for a runtime id with no known mapping are buffered/applied once mapped.
Model: `busy_rt` (**per runtime id**), `tools_rt` (**per runtime id**: open non-clarify `tool_id`s), `gateway`, `fault`, `needs_input`.

| input | effect |
|---|---|
| `desktop.state` snapshot `{gateway, busyBySession{rt:bool}}` | gateway := value; busy_rt := the snapshot (REPLACES: a runtime absent from the latest snapshot no longer counts) |
| `desktop.state` line `{gateway, busy, session: rt}` | gateway := value; busy_rt[rt] := busy |
| event `tool.start` / `tool.complete` (not clarify) | `tools_rt[rt]` += / -= `tool_call_id` |
| event `message.start` | fault F; `tools_rt[rt]` := ∅ (a turn boundary closes tools — a killed backend sends no `tool.complete`) |
| event `message.complete` `status=='error'` | fault T (sticky until next message.start) |
| `desktop.dot` `{stored_id, label}` | needs_input := (label == 'Needs your input') |

busy(stored) = OR over the runtime ids mapped to `stored` that are busy in busy_rt. Last-writer-wins across runtime ids is a bug: after a kill the app
resumes the same stored session in a NEW runtime id while the dead runtime still reports `busy:false` (desktop-kill t=43.5; we showed idle ~25 s while working).
resolve: `unknown` if gateway != 'open' → `needs-you` if needs_input → `fault` → if busy(stored): `tool` when any busy runtime of that stored id has an open tool, else `thinking` → `idle`. (`tool` never outlives `busy`.) Core's single busy dot (`Session running`) matches either of ours.
No `review` on desktop (spike 07: no signal). Parity vs core's `SessionStatusDot`: ours `thinking`|`tool`/`needs-you`
must equal core `Session running`/`Needs your input`; the only allowed divergences are
`allowed:gateway-not-open` (ours=`unknown` while gateway != 'open'; core shows stale busy up to ~26 s after a kill),
`allowed:fault-not-painted` (ours=`fault` where core shows idle) and
`allowed:render-lag` (core's dot repaints from the DOM ~80–250 ms after the host state: it differs from ours for ≤ **500 ms** after OUR resolved state last
changed AND core's dot then agrees — match or another allowed rule — within that window and before our state changes again; the sample carries `lag_s`).
Any longer or never-converging disagreement stays `MISMATCH`. Every divergence is listed in the parity report with its rule.

## 4. Trace format — `tools/traces/*.jsonl`

One JSON object per line, UTF-8, sorted by `t`. First line is the header:

```
{"v":1,"src":"meta","kind":"trace","name":"<file stem>","host":"tui|desktop","runtime":"upstream|installed",
 "runtime_sha":"f42f579cf8b","recorded_at":"<iso>","model":"custom:qwen38-local","profiles":["A"],"notes":"..."}
```

Event lines:

```
{"v":1,"t":12.345,"src":"hook|desktop.event|desktop.state|desktop.dot|liveness|observe",
 "profile":"A","session":"<stored id | runtime id for desktop.event>","lineage_root":"<root or null>",
 "kind":"<hook name | event type | state | dot | heartbeat | pid_dead | binding | screen>","payload":{...}}
```

`payload` is a **whitelist** (the repo is public): `tool_name, tool_call_id, session_key, pattern_key, completed,
interrupted, failed, status_code, retryable, choice, status, error_surface.code, stored_session_id, gateway,
busy, label, bound`, plus for `observe/screen` a short `status` string read off the pyte screen. Never prompts,
args, model output, cwd, paths, usernames, or tokens. Prompts used to drive recordings are synthetic.

Required trace set (G0 reachability needs every state reached from a recorded sequence): `turn`, `clarify`
(answered + cancelled-and-re-asked), `approval` (once + deny), `tool-error`, `api-error-401` (sticky fault,
no end hook), `api-error-retryable`, `crash-kill9` (→ unknown via pid_dead/heartbeat stop), `compression-rotate`
(id changes, same lineage root), `review-verify` (pre_verify after an edit), `twenty-sessions`, `two-profiles`
(homes A→B→A), and desktop `desktop-main` (turn/clarify/approval), `desktop-error`, `desktop-kill`.
