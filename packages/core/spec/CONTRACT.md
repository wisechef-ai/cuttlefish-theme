# Shared contract: identity allocator, state reducer, bus and file layout

`cf2909.contract/1`. Decided by the P3 lead on 2026-10-15 (card t_e4178545) so that the TS core (P2) and the
Python half (P3), built in parallel, implement **one** algorithm. Both sides are tested against the golden
vectors in this directory (`identity-vectors.json`, `state-vectors.json`), which the Python reference
generates (`python3 tools/make_contract_vectors.py [--check]`, once P3-CORE lands; CI runs `--check`). A change to anything
below is a logged lead decision, bumps the schema suffix, and regenerates the vectors in the same PR.

Precedence: plan §0/§8 > §13 > this file > phase text.

## 1. Identity allocator — `cf2909.identity/1`

All arithmetic is **integer** (hue in centidegrees, `cd`) so the two languages cannot drift on rounding.

```
GRID        = 64
ARC_LO_CD   = 11000          # 110.00°  (tokens.json identity.hue_arc_deg)
ARC_SPAN_CD = 23000          # 340.00° - 110.00°
cand(k)     = ARC_LO_CD + (ARC_SPAN_CD * (2*k + 1)) // (2*GRID)     # k in 0..63, floor division
digest      = blake2b(utf8(lineage_root), digest_size=8)            # 8 bytes, unkeyed, no salt/person
base        = digest[7] & 63                                        # last byte, low 6 bits
dist(a, b)  = min(|a - b|, 36000 - |a - b|)                         # circular, centidegrees
```

- `peers` = the persisted `hue_cd` of every OTHER lineage root whose bus entry resolves to a live state
  (§3 resolution ≠ `unknown`) at allocation time. Self is never a peer. Duplicates are kept.
- No peers → `k* = base`.
- Otherwise, for `j = 0..63`: `k = (base + j) % 64`, `score(k) = min over peers of dist(cand(k), p)`.
  `k*` = the first `k` in that order with the maximum score (strict `>` when scanning, so ties go to the
  smallest `j`).
- Result: `hue_cd = cand(k*)` (int), `hue_deg = hue_cd / 100` (a JSON number; readers must not round it).
- **Persistence (G0 contract 4):** once a lineage root has an entry in `identity.json` it is NEVER
  re-allocated, whatever the peers become. Identity is therefore independent of hook order and cache state
  after the first allocation.
- **Fallback (registry unreachable, TS readers):** the same formula with `peers = []`, i.e. `cand(base)`,
  plus the name label (§1.4 "same hash without peer spacing").
- Known limit (documented, not hidden): online farthest-point never moves a persisted hue, so the worst
  live pair at ≥ 17 peers can be as close as ~230°/32 ≈ 7.2°. G2's frozen 16/20-session identity grid is
  measured on the evenly spaced P1 stub, not on this allocator; the P23 reviewer gets the simulated worst
  case from the CORE card's property test.

### Name label

`name` = the first non-empty of: `state.db sessions.title` of the lineage root (read-only), else
`"s-" + hex(digest)[0:4]`. Trimmed to 16 code points. Readers display it verbatim.

## 2. State reducer — `cf2909.state/1`

Input: the normalised event stream for ONE lineage root, in arrival order. Output: `state` ∈
`idle | working | review | needs-you | fault | unknown`. Derived from spike 06 (§1.3 TUI column).

Normalised event: `{"hook": str, "ts": float (unix s), "session_id": str, "tool_name": str|null,
"tool_call_id": str|null, "turn_id": str|null, "completed": bool|null}`.

Reducer state: `base ∈ {idle, working, review}` (initial `idle`), `pending: ordered set of keys`,
`fault: bool`, `finalized: bool`.

| hook | effect |
|---|---|
| `on_session_reset` | base=idle, pending=∅, fault=false, finalized=false |
| `on_session_start` | finalized=false (no other effect) |
| `pre_llm_call` | base=working, pending=∅, fault=false, finalized=false |
| `pre_verify` | if base=working: base=review |
| `post_llm_call` | fault=false; if base=review: base=working |
| `on_session_end` | base=idle, pending=∅; if completed is true: fault=false |
| `pre_tool_call` with tool_name `clarify` | pending += `"clarify:" + tool_call_id` |
| `post_tool_call` with tool_name `clarify` | pending -= `"clarify:" + tool_call_id` |
| `pre_approval_request` | pending += `"approval:" + (tool_call_id or turn_id or "")` |
| `post_approval_response` | pending -= the same key |
| `api_request_error` | fault=true |
| `on_session_finalize` | finalized=true |
| anything else | ignored (`on_stream_*` is never subscribed) |

Output precedence: `finalized → unknown`; else `pending ≠ ∅ → needs-you`; else `fault → fault`; else
`base`. "Turn ended" (`on_session_end`) is never needs-you. Fault is sticky across `on_session_end{completed:false}`
(a 401 turn has no end hook at all).

`since` = `ts` of the event that last CHANGED the output state.

## 3. Resolution (what a reader may show) — `cf2909.resolve/1`

`resolved = unknown` if any of: the bus entry is missing; `finalized`; `owner_host == this host` and
`owner_pid` is not alive; `now - heartbeat > STALE_S` (`STALE_S = 30`). Otherwise `resolved = state`.
Never the last known state. A reader on another host (remote desktop) only gets resolved values from
`GET /state`, never the raw file.

## 4. Files (per `HERMES_HOME`; one write target each — G0 contract 1)

All under `<HERMES_HOME>/cuttlefish/`. Every write is atomic (`tmp` in the same dir + `os.replace`).

| file | writer | content |
|---|---|---|
| `identity.json` | Python half only | `{"schema":"cf2909.identity/1","rev":int,"sessions":{<lineage_root>:{"hue_cd":int,"hue_deg":num,"name":str,"allocated_at":num,"last_seen":num}}}` |
| `bus/<lineage_root>.json` | Python half only (the agent process) | see §5 |
| `state.json` | `hermes cuttlefish set` | `{"schema":"cf2909.prefs/1","mantle":"on"\|"off"\|1\|2,"cells":"auto"\|"half"\|"bg","dots":"blocks"\|"braille"}` |
| `ledger.json` | `hermes cuttlefish setup` | exactly what setup changed (paths created, prior `display.skin`, links), so `uninstall` restores only that |

`<lineage_root>` in a file name is the raw id with every char outside `[A-Za-z0-9._-]` replaced by `_`.

Sweep (bounded): identity entries with `last_seen` older than 30 days are dropped, and at most 512 entries
are kept (oldest `last_seen` first). Bus files are deleted on `on_session_finalize` once resolved, or when
their heartbeat is older than 24 h. A sweep touches at most 64 files per call.

## 5. Bus entry — `cf2909.bus/1`

```
{"schema":"cf2909.bus/1", "profile_home": str, "durable_id": str (current stored session_id),
 "lineage_root": str, "owner_pid": int, "owner_host": str, "seq": int (monotonic per file),
 "state": str (§2 output), "since": num, "source": str (the hook that produced it),
 "heartbeat": num (unix s, refreshed every 5 s by the owner process while alive),
 "journal": [ last ≤ 32 normalised events (§2) ] }
```

`hermes cuttlefish doctor --json` replays `journal` through the §2 reducer: `state_parity_ok` is true iff
every bus entry's stored `state` equals the replay (the journal holds enough events because the reducer
resets on `on_session_reset` / `pre_llm_call`; an entry whose journal overflowed without one of those is
reported, not silently passed). `ok` is false if any entry whose owner pid is alive has a stale heartbeat
(the writer is wedged, so a surface would show a state that is no longer true).

## 6. HTTP (`dashboard/plugin_api.py`, mounted at `/api/plugins/cuttlefish/`)

- `GET /identity` → `identity.json` content + `{"host": str}`.
- `GET /state` → `{"schema":"cf2909.state-api/1","rev":int,"now":num,"sessions":{<lineage_root>:
  {"state": <resolved>, "raw_state": str, "since": num, "durable_id": str, "hue_deg": num|null,
  "name": str, "alarm_age_s": int|null}}}`. `rev` changes only when content does (ETag is unavailable,
  spike 08).
