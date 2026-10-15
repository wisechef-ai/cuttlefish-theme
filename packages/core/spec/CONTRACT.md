# Shared contract: identity allocator, state reducer, bus and file layout

`cf2909.contract/2`. Decided by the P3 lead on 2026-10-15 (card t_e4178545); revised 2026-10-16 (P3-ALIGN, ruling by the P2
lead) so that §1–§3 are no longer restated here: the P23 contract in `packages/core/CONTRACT.md` is the single
algorithm. This file keeps the P3-owned parts: files (§4), bus entry (§5), HTTP (§6). A change to anything
below is a logged lead decision and bumps the schema suffix.

Precedence: plan §0/§8 > §13 > this file > phase text.

## 1. Allocator, reducer, resolution: see `packages/core/CONTRACT.md`

The identity allocator (20 hue slots, blake2b-256 preferred slot, `CAP = 3` capped farthest-point), the hook
state reducer (event table, `STALE_S = 20.0`, 600 ms `review` dwell, `pid_dead` latch, `binding`) and
`resolve` live in **`packages/core/CONTRACT.md` §1–§2**, and only there. This file does not restate them: a
second copy of the algorithm is how the two halves drifted once already (see `LOG.md`, P3-ALIGN).

- Python implements them in `python/domain/{allocator,reducer,resolve}.py`; TS in `packages/core/domain/`.
- One source of golden vectors: `packages/core/fixtures/identity-vectors.json` (2,101 cases). The Python test
  suite matches it 2101/2101, compares 10,000 random cases against `tui/core.bundle.mjs`, and replays every
  `tools/traces/*.jsonl` TUI trace through `python/domain/replay.py` against the bundle's `replayJson`.
- Persistence (this file's part): a lineage root with an entry in `identity.json` is NEVER re-allocated.
- Name label: `name` = `state.db sessions.title` of the lineage root (read-only) if non-empty, else
  `"s-" + hex(blake2b(utf8(root), digest_size=32))[0:4]`; trimmed to 16 code points.
- Bus-entry resolution (reader side, `resolve_entry`): `unknown` if the entry is missing or malformed, its
  `state` is `unknown` (finalized), `owner_host == this host` and `owner_pid` is not alive, or
  `now - heartbeat > STALE_S`; a `review` entry whose `review_until` has passed reads `idle`. Otherwise
  `state`. A reader on another host only gets resolved values from `GET /state`, never the raw file.

## 4. Files (per `HERMES_HOME`; one write target each — G0 contract 1)

All under `<HERMES_HOME>/cuttlefish/`. Every write is atomic (`tmp` in the same dir + `os.replace`).

| file | writer | content |
|---|---|---|
| `identity.json` | Python half only | `{"schema":"cf2909.identity/1","rev":int,"sessions":{<lineage_root>:{"slot":int (0..19),"hue_deg":num (2 dp),"name":str,"allocated_at":num,"last_seen":num}}}` |
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
 "state": str (core CONTRACT §2 resolve at the last event), "since": num (time of the last change of `state`),
 "source": str (the hook that produced it), "review_until": num|null (the 600 ms review pulse deadline),
 "heartbeat": num (unix s, refreshed every 5 s by the owner process while alive),
 "journal": [ last ≤ 32 events {"t","kind","payload","session_id"} (core CONTRACT §2) ] }
```

`hermes cuttlefish doctor --json` replays `journal` through the core-CONTRACT §2 reducer: `state_parity_ok` is true iff
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
