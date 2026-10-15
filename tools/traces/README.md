# tools/traces: recorded host event traces

Real event traces from the **upstream Hermes runtime** (`f42f579cf8b`, NousResearch `main` of 2026-09-30), recorded with
the model `custom:qwen38-local`. They are the only fixtures the state reducers and the replayer may call "recorded".
Hand-written fixtures belong to the reducers' own tests, never here.

Format = `packages/core/CONTRACT.md` section 4 (P23 shared contract): one JSON object per line, sorted by `t`, header first.
The repo is public, so a payload carries **only** `tool_name, tool_call_id, session_key, pattern_key, completed, interrupted,
failed, status_code, retryable, choice, status, error_surface{code}, stored_session_id, focused_session_id, focused_stored_session_id, gateway, busy, label, bound`. Prompts, tool
arguments, model output, cwd, paths, usernames, tokens and pids never reach a trace (`record/convert.py` is a whitelist
and fails closed on the privacy pattern). Raw, unscrubbed recordings stay out of the repo, in the vault:
`projects/cuttlefish-theme/p2/traces-raw/<name>/`.

## How the lines are made

| `src` | from | notes |
|---|---|---|
| `hook` | the `hookdump` plugin (`tools/spikes/06-hook-payloads/hookdump`) running inside the real `hermes --tui` gateway | only the 12 hooks the reducers consume: `on_session_reset on_session_start pre_llm_call post_llm_call on_session_end on_session_finalize pre_tool_call post_tool_call pre_approval_request post_approval_response api_request_error pre_verify`. Stream deltas, aux calls, `pre_api_request` are dropped. `session` is the stored (state.db) id the hook carries. |
| `liveness` | the recorder itself (`record/lib.py`), sampling the TUI owner pid and its `HERMES_TUI_ACTIVE_SESSION_FILE` | `heartbeat` every 5 s while the owner is alive and a session is bound; `binding {bound}` when the file gains/loses an id; `pid_dead` once, when the owner is reaped. `session` = the id in the bound file. |
| `desktop.event` | `host.onEvent('*')` of the real Electron build (Playwright) | only `session.info` (→ `stored_session_id`), `message.start`, `message.complete` (→ `status`, `error_surface.code`), `tool.start/complete` (→ `tool_name`, `tool_call_id`), `gateway.ready`. `session` = **runtime** id. |
| `desktop.state` | `host.state` snapshots | one line per runtime id in `busyBySession` (`gateway`, `busy`, and `stored_session_id` once mapped); a bare `{gateway}` line when the map is empty. Consecutive identical snapshots are collapsed. |
| `desktop.dot` | a 200 ms DOM sampler over core's `span[role=status]` dots | `label` is the one string the reducer reads: `Needs your input` outranks `Session running`; `""` = no non-idle dot. `session` = the focused stored id. |

`lineage_root` is resolved from a copy of the temp home's `state.db` by walking `sessions.parent_session_id`. It is `null`
for a desktop event/state whose runtime id has no known stored id yet, and for liveness lines before the first bind.

Choices the contract left open (flag to the P2 lead): `error_surface.code` is emitted **nested** (`{"error_surface":{"code":...}}`,
the source shape); `desktop.state` is one line per runtime id with `stored_session_id` in the payload; the TUI crash is a
SIGKILL of the **whole process group** (owner + gateway), so no shutdown hook can fire (killing only the node owner makes the gateway
exit gracefully and emit `on_session_end{interrupted}` + `on_session_finalize`, which would hide the pure heartbeat/pid path).

## Re-record

Needs `pip install pyte`, the upstream build (`~/.worktrees/hermes-agent/cf2909-upstream`, `ui-tui/dist` and `apps/desktop/dist` built),
the installed runtime's venv interpreter for the gateway child (`CF_HERMES_PYTHON`, upstream has no venv), the model
reachable at `custom:qwen38-local`. Each recorder uses a throwaway `HERMES_HOME` and writes `tools/traces/<name>.jsonl`.

```
python3 tools/traces/record/<script>.py          # TUI traces
CF_DISPLAY=:111 tools/traces/record/run-desktop.sh --only main|error|kill   # desktop traces, private Xvfb, 8 GB scope
python3 tools/traces/record/check.py             # every claim below, on the files on disk
```

## Traces

"States" = the contract section 2 / 3 `resolve()` sequence per lineage root (collapsed), with `STALE_S = 20` and the replay
clock advanced 25 s past the last line. P2-STATE's replayer must reproduce these.

### TUI (host `tui`)

| trace | proves | re-record | states (§1.3) |
|---|---|---|---|
| `turn` | boot, plain turn, tool turn, clean exit | `record/turn.py` | idle → working → idle → working → idle → unknown (finalize + pid_dead) |
| `clarify` | clarify answered (Enter); clarify cancelled (Ctrl-C: `post_tool_call` fires at once); re-asked and answered; all matched on `tool_call_id` | `record/clarify.py` | idle → working → needs-you → working → idle, three times, → unknown. A cancel never leaves needs-you stuck. |
| `approval` | `approvals.mode=manual`: `pre_approval_request` → `post_approval_response` `once`; again → `deny` | `record/approval.py` | idle → working → needs-you → working → idle, twice, → unknown |
| `tool-error` | a failing terminal command and a missing-file read are **not** faults | `record/tool_error.py` | idle → working → idle → working → idle → unknown; never `fault` |
| `api-error-401` | local stub answers HTTP 401: `api_request_error{status_code:401, retryable:false}` once per turn, **no end hook**; the next user turn errors again | `record/api_error_401.py` | idle → working → **fault** (sticky through 25 s of heartbeats) → working → fault → unknown |
| `api-error-retryable` | dead `base_url`: one `api_request_error{retryable:true}` per retry attempt (backoff), the turn never ends; `/exit` interrupts | `record/api_error_retryable.py` | idle → working → fault → unknown |
| `crash-kill9` | SIGKILL of owner + gateway mid-turn: no hook, heartbeats stop, `pid_dead` is the last line | `record/crash_kill9.py` | idle → working → idle → working → **unknown** (by `pid_dead`; also by staleness if `pid_dead` is ignored: replay `now` past last line + 20 s) |
| `compression-rotate` | `compression.in_place=false`: after `/compress` the hooks switch to a child id with no announcement; `parent_session_id` exists only in state.db | `record/compression_rotate.py` | ONE lineage root throughout (two stored ids): idle ↔ working per turn, → unknown. The bound file still holds the parent id (heartbeat `session` = parent), hooks carry the child. |
| `review-verify` | a `write_file` turn fires `pre_verify` once, between `post_tool_call` and `post_llm_call`; a plain turn fires none | `record/review_verify.py` | idle → working → idle → working → **review** (0.6 s dwell) → idle → unknown |
| `twenty-sessions` | 20 sessions in ONE home, 5 alive together (barrier) before any turn, then waves of 5; each ≥ 1 turn | `record/twenty_sessions.py` | 20 lineage roots, each idle → working → idle → unknown (peak concurrent owners ≥ 4; allocator input for 20 live peers) |
| `two-profiles` | homes A and B, turns interleave A, B, A, B, then a second A session; lineage roots never cross profiles | `record/two_profiles.py` | A: idle → working → idle → working → idle → unknown; B likewise; A#2 idle → working → idle → unknown |

### Desktop (host `desktop`, upstream Electron build, private Xvfb `:111`)

| trace | proves | re-record | states (§3) |
|---|---|---|---|
| `desktop-main` | plain turn; clarify answered by clicking a choice; approval **Reject** (the victim path survived). Dots sampled alongside: `Needs your input` appears with the prompt and clears on the answer | `run-desktop.sh --only main` | idle → working → idle → working → needs-you → working → idle → working → needs-you → working → idle |
| `desktop-error` | dead `modelBaseUrl`: the turn ends with `message.complete{status:error, error_surface.code}`; core paints no dot for the fault | `run-desktop.sh --only error` (≈ 6 min of provider retries) | idle → working → **fault** (`message.complete` status error at t ≈ 352 s; `busy` false, dot back to `""`: the fault is held sticky by the reducer, core paints none) |
| `desktop-kill` | SIGKILL of the python backend mid-turn: `gateway` closed → connecting → open while `busy` stays true (upstream keeps stale busy ≈ 26 s), then the app resumes the session in a new runtime id | `run-desktop.sh --only kill` | idle → working → **unknown** (gateway ≠ open) → working → idle → working → idle |

## Privacy gate

```
grep -inE 'adam|/home/|api[_-]?key|sk-|token|password' tools/traces/*.jsonl      # must print nothing
```

`tests/test_traces_shipped.py` runs the same pattern, plus the per-trace claims in `record/check.py`.
