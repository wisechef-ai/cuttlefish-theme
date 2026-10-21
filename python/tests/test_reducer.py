"""CONTRACT §2: one test per event-table row, then the precedence overlaps. Events are {t, kind, payload}."""
from cuttlefish_theme.python.domain import reducer as R
from cuttlefish_theme.python.domain import resolve as V


def ev(kind, t=1.0, **payload):
    return {"t": t, "kind": kind, "payload": payload}


def run(*events, now=None):
    m = R.initial()
    for e in events:
        m = R.reduce(m, e)
    return m, V.resolve(m, events[-1]["t"] if now is None else now)


def state(*events, now=None):
    return run(*events, now=now)[1]


def test_initial_model_has_the_contract_fields_and_is_unknown_until_first_event():
    m = R.initial()
    assert m == {"in_turn": False, "tools": [], "pending": [], "fault": False, "review_until": None, "finalized": False,
                 "last_seen": None, "bound": True, "pid_alive": None}
    assert V.resolve(m, 5.0) == "unknown"


def test_reduce_is_pure():
    m = R.initial()
    m2 = R.reduce(m, ev("pre_tool_call", tool_name="clarify", tool_call_id="c"))
    assert m == R.initial() and m2["pending"] == ["clarify:c"]


def test_pre_llm_call_starts_thinking_and_clears_fault_and_finalized():
    assert state(ev("pre_llm_call")) == "thinking"
    assert state(ev("on_session_finalize"), ev("pre_llm_call", 2)) == "thinking"
    assert state(ev("api_request_error"), ev("pre_llm_call", 2)) == "thinking"


def test_session_start_is_proof_of_life_only():
    m, s = run(ev("on_session_start", 4.0))
    assert s == "idle" and m["last_seen"] == 4.0 and m["in_turn"] is False


def test_session_end_returns_to_idle_drops_pending_and_completed_clears_fault():
    assert state(ev("pre_llm_call"), ev("on_session_end", 2, completed=True)) == "idle"
    assert state(ev("pre_tool_call", tool_name="clarify", tool_call_id="a"), ev("on_session_end", 2, completed=False)) == "idle"
    assert state(ev("api_request_error"), ev("on_session_end", 2, completed=False)) == "fault"
    assert state(ev("api_request_error"), ev("on_session_end", 2, completed=True)) == "idle"
    assert state(ev("api_request_error"), ev("on_session_end", 2, completed="yes")) == "fault"  # only `is True`


def test_session_reset_clears_everything_and_the_pid_latch():
    e = [ev("pre_llm_call"), ev("pre_tool_call", 2, tool_name="clarify", tool_call_id="c"), ev("api_request_error", 3),
         ev("pre_verify", 4), ev("pid_dead", 5)]
    m, s = run(*e, ev("on_session_reset", 6))
    assert s == "idle" and m["pid_alive"] is None and m["review_until"] is None and m["pending"] == []


def test_clarify_pending_until_the_matching_post_tool_call():
    seq = [ev("pre_llm_call"), ev("pre_tool_call", 2, tool_name="clarify", tool_call_id="c1")]
    assert state(*seq) == "needs-you"
    assert state(*seq, ev("post_tool_call", 3, tool_name="clarify", tool_call_id="c1")) == "thinking"
    assert state(*seq, ev("post_tool_call", 3, tool_name="clarify", tool_call_id="zz")) == "needs-you"


def test_other_tools_never_raise_needs_you():
    assert state(ev("pre_llm_call"), ev("pre_tool_call", 2, tool_name="terminal", tool_call_id="t")) == "tool"


def test_cancelled_then_reasked_clarify_does_not_stick():
    seq = [ev("pre_llm_call"), ev("pre_tool_call", 2, tool_name="clarify", tool_call_id="c1"),
           ev("post_tool_call", 3, tool_name="clarify", tool_call_id="c1"),
           ev("pre_tool_call", 4, tool_name="clarify", tool_call_id="c2")]
    assert state(*seq) == "needs-you"
    assert state(*seq, ev("post_tool_call", 5, tool_name="clarify", tool_call_id="c2")) == "thinking"


def test_approval_key_is_tool_call_id_else_session_key_slash_pattern_key():
    a = ev("pre_approval_request", tool_call_id="x")
    assert state(a, ev("post_approval_response", 2, tool_call_id="x")) == "idle"
    assert state(a, ev("post_approval_response", 2, tool_call_id="y")) == "needs-you"
    b = ev("pre_approval_request", session_key="k", pattern_key="p")
    assert R.reduce(R.initial(), b)["pending"] == ["approval:k/p"]
    assert state(b, ev("post_approval_response", 2, session_key="k", pattern_key="p")) == "idle"
    assert R.reduce(R.initial(), ev("pre_approval_request"))["pending"] == ["approval:/"]


def test_clarify_and_approval_keys_do_not_collide_and_pending_is_sorted_and_deduped():
    m = R.initial()
    for e in (ev("pre_approval_request", tool_call_id="k"), ev("pre_tool_call", tool_name="clarify", tool_call_id="k"),
              ev("pre_tool_call", tool_name="clarify", tool_call_id="k")):
        m = R.reduce(m, e)
    assert m["pending"] == ["approval:k", "clarify:k"]


def test_api_request_error_is_sticky_fault_and_post_llm_call_clears_it():
    seq = [ev("pre_llm_call"), ev("api_request_error", 2), ev("api_request_error", 3)]
    assert state(*seq) == "fault"
    assert state(*seq, ev("post_llm_call", 4)) == "thinking"


def test_pre_verify_sets_a_600ms_review_pulse_under_thinking():
    m, s = run(ev("pre_verify", 10.0))
    assert m["review_until"] == 10.6 and s == "review"
    assert V.resolve(m, 10.59) == "review" and V.resolve(m, 10.6) == "idle"
    assert state(ev("pre_llm_call", 9), ev("pre_verify", 10.0)) == "thinking"  # working > review


def test_precedence_needs_you_over_fault_over_working_over_review_over_idle():
    seq = [ev("pre_llm_call"), ev("pre_verify", 2), ev("api_request_error", 3)]
    assert state(*seq) == "fault"
    assert state(*seq, ev("pre_tool_call", 4, tool_name="clarify", tool_call_id="a")) == "needs-you"


def test_finalize_is_unknown_and_wins_over_everything():
    assert state(ev("pre_llm_call"), ev("pre_tool_call", 2, tool_name="clarify", tool_call_id="a"),
                 ev("api_request_error", 3), ev("on_session_finalize", 4)) == "unknown"


def test_stale_is_unknown_strictly_after_20s():
    assert V.STALE_S == 20.0
    m = R.reduce(R.initial(), ev("pre_llm_call", 100.0))
    assert V.resolve(m, 120.0) == "thinking" and V.resolve(m, 120.001) == "unknown"


def test_heartbeat_marks_alive_and_pid_dead_latches_until_heartbeat_or_reset():
    m, s = run(ev("pre_llm_call"), ev("pid_dead", 2))
    assert s == "unknown" and m["pid_alive"] is False
    for other in (ev("pre_llm_call", 3), ev("post_llm_call", 4), ev("on_session_start", 5), ev("api_request_error", 6)):
        m = R.reduce(m, other)
        assert V.resolve(m, other["t"]) == "unknown"          # other hooks do NOT revive it
    m = R.reduce(m, ev("heartbeat", 7))
    assert m["pid_alive"] is True and V.resolve(m, 7) != "unknown"


def test_heartbeat_alone_refreshes_last_seen_only():
    m = R.reduce(R.initial(), ev("heartbeat", 3.0))
    assert m["last_seen"] == 3.0 and m["pid_alive"] is True and V.resolve(m, 3.0) == "idle"


def test_binding_false_is_unknown_true_restores_and_only_literal_true_binds():
    m = R.reduce(R.initial(), ev("binding", 1, bound=False))
    assert V.resolve(m, 1) == "unknown"
    assert V.resolve(R.reduce(m, ev("binding", 2, bound=True)), 2) == "idle"
    assert V.resolve(R.reduce(R.initial(), ev("binding", 1, bound="yes")), 1) == "unknown"


def test_every_event_sets_last_seen_and_unknown_kinds_are_proof_of_life_only():
    m = R.reduce(R.initial(), ev("on_stream_delta", 7.5))
    assert m["last_seen"] == 7.5 and V.resolve(m, 7.5) == "idle"


def test_normalise_builds_the_event_dict_with_a_whitelisted_payload():
    n = R.normalise("pre_tool_call", {"session_id": "s1", "tool_name": "clarify", "tool_call_id": "c1",
                                      "args": {"secret": "x"}, "user_message": "hello"}, 12.5)
    assert n == {"t": 12.5, "kind": "pre_tool_call", "session_id": "s1",
                 "payload": {"tool_name": "clarify", "tool_call_id": "c1"}}
    n2 = R.normalise("on_session_end", {"session_id": "s", "completed": True, "failed": False}, 1.0)
    assert n2["payload"] == {"completed": True}
    n3 = R.normalise("pre_approval_request", {"session_key": "k", "pattern_key": "p", "command": "rm -rf /"}, 1.0)
    assert n3["session_id"] == "k" and n3["payload"] == {"session_key": "k", "pattern_key": "p"}
    assert R.normalise("on_session_end", {"session_id": "s", "completed": "yes"}, 1.0)["payload"] == {}
