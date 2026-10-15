"""CONTRACT §2: one test per table row, then the precedence overlaps."""
from cuttlefish_theme.python.domain import reducer as R


def ev(hook, ts=1.0, sid="s", tool=None, call=None, turn=None, completed=None):
    return {"hook": hook, "ts": ts, "session_id": sid, "tool_name": tool,
            "tool_call_id": call, "turn_id": turn, "completed": completed}


def states(*events):
    out, _ = R.fold(list(events))
    return [o["state"] for o in out]


def final(*events):
    return states(*events)[-1]


def test_fresh_machine_is_idle():
    assert R.output(R.initial()) == "idle"


def test_pre_llm_call_starts_working():
    assert states(ev("pre_llm_call")) == ["working"]


def test_session_end_returns_to_idle():
    assert states(ev("pre_llm_call"), ev("on_session_end", completed=True)) == ["working", "idle"]


def test_on_session_reset_clears_everything():
    out = final(ev("pre_llm_call"), ev("pre_tool_call", tool="clarify", call="c1"),
                ev("api_request_error"), ev("on_session_reset"))
    assert out == "idle"


def test_on_session_start_alone_changes_nothing_but_unfinalizes():
    assert final(ev("on_session_start")) == "idle"
    assert final(ev("on_session_finalize"), ev("on_session_start")) == "idle"


def test_pre_verify_moves_working_to_review_only():
    assert states(ev("pre_llm_call"), ev("pre_verify")) == ["working", "review"]
    assert final(ev("pre_verify")) == "idle"  # base is idle: no effect


def test_post_llm_call_returns_review_to_working_and_clears_fault():
    assert states(ev("pre_llm_call"), ev("pre_verify"), ev("post_llm_call")) == ["working", "review", "working"]
    assert final(ev("pre_llm_call"), ev("api_request_error"), ev("post_llm_call")) == "working"


def test_clarify_pending_until_matching_post_tool_call():
    seq = [ev("pre_llm_call"), ev("pre_tool_call", tool="clarify", call="c1")]
    assert states(*seq) == ["working", "needs-you"]
    assert final(*seq, ev("post_tool_call", tool="clarify", call="c1")) == "working"


def test_other_tools_never_raise_needs_you():
    assert final(ev("pre_llm_call"), ev("pre_tool_call", tool="terminal", call="t1")) == "working"


def test_cancelled_then_reasked_clarify_does_not_stick():
    # spike 06: Ctrl-C fires post_tool_call at once; the model may re-ask with a NEW tool_call_id
    out = states(ev("pre_llm_call"),
                 ev("pre_tool_call", tool="clarify", call="c1"),
                 ev("post_tool_call", tool="clarify", call="c1"),
                 ev("pre_tool_call", tool="clarify", call="c2"),
                 ev("post_tool_call", tool="clarify", call="c2"))
    assert out == ["working", "needs-you", "working", "needs-you", "working"]


def test_two_open_clarifies_need_both_closed():
    seq = [ev("pre_tool_call", tool="clarify", call="a"), ev("pre_tool_call", tool="clarify", call="b"),
           ev("post_tool_call", tool="clarify", call="a")]
    assert final(*seq) == "needs-you"
    assert final(*seq, ev("post_tool_call", tool="clarify", call="b")) == "idle"


def test_approval_keyed_on_tool_call_id_then_turn_id_then_empty():
    assert final(ev("pre_approval_request", call="x"), ev("post_approval_response", call="x")) == "idle"
    assert final(ev("pre_approval_request", call="x"), ev("post_approval_response", call="y")) == "needs-you"
    assert final(ev("pre_approval_request", turn="T"), ev("post_approval_response", turn="T")) == "idle"
    assert final(ev("pre_approval_request"), ev("post_approval_response")) == "idle"
    assert final(ev("pre_approval_request"), ev("pre_tool_call", tool="clarify", call="")) == "needs-you"


def test_clarify_and_approval_keys_do_not_collide():
    seq = [ev("pre_tool_call", tool="clarify", call="k"), ev("pre_approval_request", call="k"),
           ev("post_approval_response", call="k")]
    assert final(*seq) == "needs-you"


def test_api_request_error_sets_fault_and_is_sticky_across_failed_session_end():
    seq = [ev("pre_llm_call"), ev("api_request_error")]
    assert states(*seq) == ["working", "fault"]
    assert final(*seq, ev("on_session_end", completed=False)) == "fault"


def test_fault_clears_on_completed_session_end_or_next_turn():
    base = [ev("pre_llm_call"), ev("api_request_error")]
    assert final(*base, ev("on_session_end", completed=True)) == "idle"
    assert final(*base, ev("pre_llm_call")) == "working"


def test_401_turn_with_no_end_hook_stays_fault():
    seq = [ev("pre_llm_call"), ev("api_request_error"), ev("api_request_error")]
    assert states(*seq) == ["working", "fault", "fault"]


def test_session_end_is_never_needs_you_and_drops_pending():
    assert final(ev("pre_tool_call", tool="clarify", call="a"), ev("on_session_end", completed=False)) == "idle"


def test_finalize_is_unknown_and_wins_over_everything():
    assert final(ev("pre_llm_call"), ev("pre_tool_call", tool="clarify", call="a"),
                 ev("api_request_error"), ev("on_session_finalize")) == "unknown"


def test_new_turn_after_finalize_revives():
    assert final(ev("on_session_finalize"), ev("pre_llm_call")) == "working"


def test_precedence_needs_you_over_fault_over_base():
    seq = [ev("pre_llm_call"), ev("api_request_error"), ev("pre_tool_call", tool="clarify", call="a")]
    assert states(*seq) == ["working", "fault", "needs-you"]
    assert final(*seq, ev("post_tool_call", tool="clarify", call="a")) == "fault"


def test_unsubscribed_and_unknown_hooks_are_ignored():
    assert states(ev("pre_llm_call"), ev("on_stream_delta"), ev("whatever")) == ["working"] * 3


def test_since_is_the_ts_of_the_event_that_last_changed_the_output():
    out, _ = R.fold([ev("pre_llm_call", ts=10.0), ev("post_llm_call", ts=11.0),
                     ev("pre_tool_call", ts=12.0, tool="clarify", call="a"),
                     ev("pre_tool_call", ts=13.0, tool="terminal", call="t")])
    assert [(o["state"], o["since"]) for o in out] == [
        ("working", 10.0), ("working", 10.0), ("needs-you", 12.0), ("needs-you", 12.0)]


def test_rotation_ids_change_but_the_stream_is_one_lineage():
    out = states(ev("pre_llm_call", sid="parent"), ev("pre_tool_call", sid="child", tool="clarify", call="a"),
                 ev("post_tool_call", sid="child", tool="clarify", call="a"))
    assert out == ["working", "needs-you", "working"]


def test_normalise_builds_the_event_dict():
    n = R.normalise("pre_tool_call", {"session_id": "s1", "tool_name": "clarify", "tool_call_id": "c1",
                                      "turn_id": "t1", "args": {"secret": "x"}}, 12.5)
    assert n == {"hook": "pre_tool_call", "ts": 12.5, "session_id": "s1", "tool_name": "clarify",
                 "tool_call_id": "c1", "turn_id": "t1", "completed": None}
    n2 = R.normalise("on_session_end", {"session_id": "s", "completed": True, "failed": False}, 1.0)
    assert n2["completed"] is True and n2["tool_name"] is None
    n3 = R.normalise("pre_approval_request", {"session_key": "k", "command": "rm -rf /"}, 1.0)
    assert n3["session_id"] == "k" and "command" not in n3
    assert R.normalise("on_session_end", {"session_id": "s", "completed": "yes"}, 1.0)["completed"] is None
