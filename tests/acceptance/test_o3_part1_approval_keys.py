"""ACCEPTANCE CONTRACT PART 1 — O3 request keys for approval-only pairs (closes luna F1) (locked).

Why: at Hermes v0.22.7 the approval hook kwargs of the GATEWAY path carry NO `request_id`
(tools/approval_gateway_wait.py:159-164: command, description, pattern_key, pattern_keys, session_key, surface;
tools/approval_context.py:66-69 adds turn_id, tool_call_id, session_id). Only the plugin-transport path supplies one
(tools/approval_prompt.py:237-240) and MCP elicitation fires a pre/post pair with NO human_input wrapper at all
(approval_prompt.py:358-362). The locked O3.4 demands one shared request_id for an approval-only pair, so the
plugin has to DERIVE it. The kwargs below are copied from those producers; nothing is invented.

THE DERIVATION RULE (binding): the request key of an approval hook call is
  1. the producer's `request_id` when the call carries a non-empty one (transport path), else
  2. a stable key over exactly (session_key, turn_id, tool_call_id, pattern_key, surface): deterministic across calls
     and processes (no random, no hash()), identical for a request's pre and post, and independent of the command text,
     description, choice or any other kwarg.
Consumers (the desktop reducer) key open requests by `(session_id, request_id)`; "open" below means: an active=True
event whose key has not seen an active=False event since.
"""
from __future__ import annotations

import importlib

import pytest

from .helpers import plugin_package

SID = "20261105_101500_ab12cd"
SK = "agent:main:desktop:dm:" + SID  # a gateway session key; the stored id is SID

# --- tools/approval_gateway_wait.py:159-164 (+ approval_context.py:66-69 defaults) -------------------------------
GATEWAY = dict(command="rm -rf /tmp/secret-thing", description="recursive delete", pattern_key="rm_rf",
               pattern_keys=["rm_rf"], session_key=SK, surface="gateway", turn_id="t1", tool_call_id="c1", session_id=SID)
# --- tools/approval_prompt.py:237-240: the transport path DOES carry request_id / request_digest ------------------
TRANSPORT = dict(command="rm -rf /tmp/secret-thing", description="recursive delete", pattern_key="rm_rf",
                 pattern_keys=["rm_rf"], session_key=SK, surface="transport:acme", request_id="tr-77aa",
                 request_digest="sha256:0f", turn_id="t1", tool_call_id="c1", session_id=SID)
# --- tools/approval_prompt.py:358-362: MCP elicitation, default surface "mcp-elicitation", no human_input wrapper ---
ELICIT = dict(command="Allow the server to read your calendar?", description="calendar scope", pattern_key="mcp_elicitation",
              pattern_keys=["mcp_elicitation"], session_key=SK, surface="mcp-elicitation", turn_id="t1", tool_call_id="c9",
              session_id=SID)
# --- tools/human_input_hooks.py:61-73: the wrapper around the gateway path (uuid request_id, redacted prompt) ----
HUMAN = dict(kind="approval", request_id="9f1c0de5aa", session_id=SID, session_key=SK, platform="desktop",
             prompt="rm -rf /tmp/secret-thing")


@pytest.fixture
def sent():
    plugin_package()
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    got: list[tuple[str, str, dict]] = []
    events.set_broadcaster(lambda plugin_id, event, payload=None: got.append((plugin_id, event, dict(payload or {}))))
    yield got
    events.set_broadcaster(None)


def hooks():
    plugin_package()
    return importlib.import_module("cuttlefish_theme.cuttlefish.hooks")


def pre(**kw):
    hooks().pre_approval_request(**kw)


def post(choice="once", **kw):
    hooks().post_approval_response(**kw, choice=choice)


def open_requests(sent) -> set[tuple[str, str]]:
    """The desktop's view: (session_id, request_id) pairs opened and not yet closed."""
    live: set[tuple[str, str]] = set()
    for _plugin, event, p in sent:
        if event != "needs_you":
            continue
        key = (p["session_id"], p["request_id"])
        if p["active"]:
            live.add(key)
        else:
            live.discard(key)
    return live


def request_ids(sent) -> list[str]:
    return [p["request_id"] for _, e, p in sent if e == "needs_you"]


def test_P1_1_producer_request_id_wins_on_the_transport_path(sent):
    pre(**TRANSPORT)
    assert open_requests(sent) == {(SID, "tr-77aa")}
    post("once", **TRANSPORT)
    assert open_requests(sent) == set()
    assert set(request_ids(sent)) == {"tr-77aa"}, "the producer's own id is used verbatim, never replaced by a derived one"


def test_P1_2_gateway_pair_without_request_id_opens_and_closes_one_stable_key(sent):
    assert "request_id" not in GATEWAY, "fixture drift: the gateway producer carries no request_id"
    pre(**GATEWAY)
    mid = open_requests(sent)
    assert len(mid) == 1 and next(iter(mid))[0] == SID
    post("deny", **GATEWAY)
    assert open_requests(sent) == set()
    assert len(set(request_ids(sent))) == 1 and request_ids(sent)[0], "pre and post name the same, non-empty request"


def test_P1_3_derivation_is_stable_across_calls_and_ignores_text_and_choice(sent):
    pre(**GATEWAY)
    first = request_ids(sent)[0]
    sent.clear()
    # the same request seen again later, text redacted/rewritten, post-only kwargs added: still the same key
    post("session", **{**GATEWAY, "command": "<redacted>", "description": "", "pattern_keys": ["rm_rf", "extra"]})
    assert request_ids(sent) == [first], "key depends on (session_key, turn_id, tool_call_id, pattern_key, surface) only"
    sent.clear()
    pre(**GATEWAY)
    assert request_ids(sent) == [first], "deterministic: no random, no per-process hash()"


@pytest.mark.parametrize("field,other", [("session_key", SK + "-b"), ("turn_id", "t2"), ("tool_call_id", "c2"),
                                         ("pattern_key", "chmod_777"), ("surface", "cli")])
def test_P1_4_every_derivation_input_separates_requests(sent, field, other):
    a, b = dict(GATEWAY), {**GATEWAY, field: other}
    pre(**a)
    pre(**b)
    assert len(open_requests(sent)) == 2, f"two approvals differing only in {field} must be two open requests"
    post("once", **a)
    assert len(open_requests(sent)) == 1, "closing one leaves the other open"
    post("once", **b)
    assert open_requests(sent) == set()


def test_P1_5_mcp_elicitation_pair_without_a_human_input_wrapper_opens_and_closes(sent):
    pre(**ELICIT)
    assert len(open_requests(sent)) == 1
    post("cancelled", **ELICIT)  # approval_prompt.py:366-370 fires post in a finally, also with "cancelled"
    assert open_requests(sent) == set()
    assert [p["kind"] for _, e, p in sent if e == "needs_you"] == ["approval", "approval"]


def test_P1_6_a_coalesced_follower_opens_nothing_new_and_closes_nothing_the_leader_holds(sent):
    # leader: approval_gateway_wait.py:97 fires the plain pre; follower (parallel tool call, other tool_call_id) :117
    # fires pre(coalesced=True) and, once the leader decides, post(..., coalesced=True) via _finish :137.
    leader, follower = GATEWAY, {**GATEWAY, "tool_call_id": "c2"}
    pre(**leader)
    leader_open = open_requests(sent)
    assert len(leader_open) == 1
    n = len(sent)
    pre(**follower, coalesced=True)
    assert open_requests(sent) == leader_open, "no double count: still exactly the leader's request"
    assert not [1 for _, e, p in sent[n:] if e == "needs_you" and p["active"] and (p["session_id"], p["request_id"]) not in leader_open]
    post("deny", **follower, coalesced=True)
    assert open_requests(sent) == leader_open, "the follower's post must not close what the leader still holds"
    post("deny", **leader)
    assert open_requests(sent) == set()


def test_P1_7_a_coalesced_follower_that_gets_once_fires_no_post_and_leaks_nothing(sent):
    # approval_gateway_wait.py:131-133: a leader "once" makes the follower return None WITHOUT a post hook.
    pre(**GATEWAY)
    pre(**{**GATEWAY, "tool_call_id": "c2"}, coalesced=True)
    post("once", **GATEWAY)
    assert open_requests(sent) == set(), "the follower never opened anything, so its missing post leaks nothing"


def test_P1_8_same_tool_call_follower_does_not_double_count_either(sent):
    pre(**GATEWAY)
    pre(**GATEWAY, coalesced=True)  # identical derived key
    post("session", **GATEWAY, coalesced=True)
    assert len(open_requests(sent)) == 1, "a coalesced call never closes the leader"
    post("session", **GATEWAY)
    assert open_requests(sent) == set()


def test_P1_9_gateway_path_human_wrapper_plus_inner_approval_pair_ends_with_zero_open(sent):
    # approval_gateway_wait.py:228-236: on_human_input_request, then pre_approval_request inside the `with`,
    # post_approval_response from _finish, then on_human_input_resolved when the `with` exits.
    h = hooks()
    h.on_human_input_request(**HUMAN)
    pre(**GATEWAY)
    assert open_requests(sent), "something is open while the human is being asked"
    post("once", **GATEWAY)
    h.on_human_input_resolved(**HUMAN, outcome="once")
    assert open_requests(sent) == set(), sorted(open_requests(sent))


def test_P1_10_payloads_stay_free_of_command_text_and_the_key_is_not_a_digest_of_it(sent):
    pre(**GATEWAY)
    pre(**ELICIT)
    blob = repr(sent)
    for needle in ("secret-thing", "recursive delete", "calendar", "rm -rf"):
        assert needle not in blob, needle
    assert SK not in " ".join(request_ids(sent)), "the session key itself is not echoed back as the request id"


def test_P1_11_rejects_what_it_cannot_attribute(sent):
    # no session id => the desktop cannot place it (locked O3.8 for the human_input path, same rule here)
    pre(**{**GATEWAY, "session_id": ""})
    pre(**{k: v for k, v in GATEWAY.items() if k != "session_id"})
    assert sent == [], "an approval without a session is not sent, never sent under a guessed one"
    hooks().pre_approval_request()  # no kwargs: never raises
    hooks().post_approval_response(choice=None, session_id=None, pattern_key=None)
