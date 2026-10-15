# spike 06 replay fixtures

Real hook logs from cf2909 spike 06 (hook payloads), reduced to the CONTRACT §2 normalised event
(`packages/core/spec/CONTRACT.md`) and paired with a hand-labelled expected state timeline. Both reducers
(Python P3-CORE, TS P2) must reproduce `expected.json` when they replay the `.jsonl` files.

## Files

| file | source (receipt `spikes/06-hook-payloads.md`, artifacts `spikes/assets/06/`) | events | what it exercises |
|---|---|---|---|
| `main.jsonl` | `main.jsonl` | 30 | idle, working, plain turn, tool call, clarify answered (43.2→53.2 s), clarify cancelled + re-asked (58.9→66.2, 68.2→134.9), finalize→unknown |
| `error.jsonl` | `error.jsonl` | 16 | dead base_url: 11 `api_request_error`, no turn end, fault sticky through exit |
| `failed.jsonl` | `failed.jsonl` | 8 | HTTP 401: fault with no terminator, cleared by the next `pre_llm_call`, faults again |
| `approval.jsonl` | `approval.jsonl` | 11 | needs-you from `pre_approval_request` to `post_approval_response` (~91 s) |
| `rotate.jsonl` | `rotate.jsonl` | 13 | the in-place `/compress` run: id never changes (a negative control) |
| `verify_approval.jsonl` | `verify_approval.jsonl` | 17 | review (`pre_verify`, 90 ms) + approval (25.9→32.2 s) |
| `approval_chain.jsonl` | `lineage-hooks.jsonl`, pid 267723 (the single-TUI lineage run, spike 05/06) | 90 | 18 stacked approvals over 6 turns; an approval left open at exit |
| `rotate_lineage.jsonl` | `lineage-hooks.jsonl`, pid 283875 from the 2nd `on_session_reset` of `…78f947` | 15 | rotating compression: child id appears unannounced on `pre_llm_call` |
| `lineage.json` | receipt “Compression”: `115737_78f947` → `120603_0bed33` | – | child → parent per trace, as `state.db sessions.parent_session_id` would give (only `rotate_lineage` has a link) |
| `expected.json` | receipt §1.3 table + prose, CONTRACT §2 where the receipt is silent | – | per trace, `after_each_event`: `{hook, state, since}`; `notes` lists every ambiguity |

States covered across the set: idle, working, review, needs-you, fault, unknown (review only in `verify_approval`).

## Event shape

`{"hook","ts","session_id","tool_name","tool_call_id","turn_id","completed"}` – exactly the CONTRACT §2 fields.
`ts` is seconds, rebased so the first event is 0.0. `session_id` is `S1`, `S2`… in first-seen order per file;
`tool_call_id` is `c1`…; `turn_id` is `<session label>:t<n>`. `tool_name` is only set on tool hooks and `completed`
only on `on_session_end`.

## What was dropped (this repo is public)

Everything outside the seven fields above: the user prompt text, tool `args`, `command`/`description` of approvals,
`conversation_history`, `final_response`, `changed_paths`, error text/`request`, `model`, `base_url`, `task_id`,
`api_request_id`, `pid`, `platform`, raw session/tool-call ids (their date-stamped form), file paths, and the
`@@MARK` driver annotations. Hooks the CONTRACT does not subscribe to (`on_stream_*`, `pre/post_api_request`,
`transform_*`, `pre/post_auxiliary_call`, `agent_loop_stopped`) are dropped, so event counts are smaller than the raw logs.
`test_spike06_fixtures.py` enforces the key whitelist and a ≤80-char limit on every string.

## Independence of the oracle

`expected.json` was written from the receipt, never from a reducer run. `author_expected.py` holds the typed labels
(index ranges → state) and only expands them and derives `since`; it imports no reducer. Receipt/artifact mismatches
are recorded, not hidden: e.g. the receipt says “8 retries” for the error run but `error.jsonl` holds 11
`api_request_error` events (the artifact is used).

## Regenerate / check

```
CF_SPIKE06_DIR=<vault>/projects/cuttlefish-theme/spikes/assets/06 python3 tools/traces/spike06/convert.py          # write
CF_SPIKE06_DIR=…                                                    python3 tools/traces/spike06/convert.py --check  # drift check
python3 tools/traces/spike06/author_expected.py [--check]
python3 -m pytest tools/traces/spike06            # static fixture checks (no vault needed)
```
