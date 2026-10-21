"""Hook callbacks: they drive identity + bus, and nothing they do can reach the agent turn."""
import json
import logging

from cuttlefish_theme.python import hooks as H
from cuttlefish_theme.python import paths as P
from cuttlefish_theme.python import plugin_entry as E

TURN = "t:1"


def rt(home, clock, **kw):
    return H.Runtime(home, clock=clock, pid=4242, host="box", pid_alive=lambda p: True,
                     heartbeat_interval=60, **kw)


def bus(home, root):
    return json.loads(P.bus_file(home, root).read_text())


def test_a_turn_drives_the_bus_file(home, clock):
    r = rt(home, clock)
    cb = r.callbacks()
    cb["on_session_reset"](session_id="s1")
    assert bus(home, "s1")["state"] == "idle"
    cb["pre_llm_call"](session_id="s1", turn_id=TURN, user_message="hi", conversation_history=[1, 2])
    assert bus(home, "s1")["state"] == "thinking"
    cb["on_session_end"](session_id="s1", completed=True, failed=False)
    assert bus(home, "s1")["state"] == "idle"
    ident = json.loads(P.identity_file(home).read_text())
    assert "s1" in ident["sessions"]


def test_first_hook_of_any_kind_allocates_identity_even_without_session_start(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="never-started")
    assert "never-started" in json.loads(P.identity_file(home).read_text())["sessions"]


def test_clarify_cancel_and_reask_through_callbacks(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    cb["pre_tool_call"](session_id="s", tool_name="clarify", tool_call_id="c1")
    assert bus(home, "s")["state"] == "needs-you"
    cb["post_tool_call"](session_id="s", tool_name="clarify", tool_call_id="c1", error_type=None)
    cb["pre_tool_call"](session_id="s", tool_name="clarify", tool_call_id="c2")
    assert bus(home, "s")["state"] == "needs-you"
    cb["post_tool_call"](session_id="s", tool_name="clarify", tool_call_id="c2")
    assert bus(home, "s")["state"] == "thinking"


def test_ordinary_tool_calls_do_not_write(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    seq = bus(home, "s")["seq"]
    cb["pre_tool_call"](session_id="s", tool_name="terminal", tool_call_id="t1", args={"command": "ls"})
    cb["post_tool_call"](session_id="s", tool_name="terminal", tool_call_id="t1")
    assert bus(home, "s")["seq"] == seq


def test_events_without_a_session_id_are_ignored(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="")
    assert not P.bus_dir(home).exists()


def test_rotation_keeps_one_identity_and_one_bus_file(home, clock, make_state_db):
    make_state_db(home, [("root", None, None), ("child", "root", None)])
    cb = rt(home, clock).callbacks()
    cb["on_session_reset"](session_id="root")
    cb["pre_llm_call"](session_id="child")  # unannounced id change
    assert [p.name for p in P.bus_dir(home).iterdir()] == ["root.json"]
    assert bus(home, "root")["durable_id"] == "child"
    assert list(json.loads(P.identity_file(home).read_text())["sessions"]) == ["root"]


def test_api_request_error_is_sticky_fault_until_next_turn(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    cb["api_request_error"](session_id="s", status_code=401, retryable=False)
    assert bus(home, "s")["state"] == "fault"
    cb["pre_llm_call"](session_id="s")
    assert bus(home, "s")["state"] == "thinking"


def test_retryable_api_request_error_does_not_fault(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    cb["api_request_error"](session_id="s", retryable=True)
    assert bus(home, "s")["state"] == "thinking"


def test_finalize_removes_the_bus_file_and_keeps_identity(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    cb["on_session_finalize"](session_id="s")
    assert not P.bus_file(home, "s").exists()
    assert "s" in json.loads(P.identity_file(home).read_text())["sessions"]


def test_a_hook_exception_never_propagates_and_is_logged_once(home, clock, caplog):
    r = rt(home, clock)
    cb = r.callbacks()

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    r.store.ensure = boom
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert cb["pre_llm_call"](session_id="s") is None
        assert cb["on_session_end"](session_id="s", completed=True) is None
    msgs = [m for m in caplog.messages if "disk on fire" in m]
    assert len(msgs) == 1  # once per distinct failure, not once per hook call


def test_corrupt_inputs_never_propagate(home, clock):
    cb = rt(home, clock).callbacks()
    for name, fn in cb.items():
        assert fn(session_id=object(), tool_name=3, completed="maybe") is None
        assert fn() is None
        assert fn("positional", garbage=True) is None


def test_pre_verify_returns_none_in_every_case(home, clock):
    cb = rt(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s")
    assert cb["pre_verify"](session_id="s", coding=True, attempt=0, final_response="x", changed_paths=["a"]) is None
    e = bus(home, "s")
    assert e["state"] == "thinking" and e["review_until"] == clock() + 0.6   # working > review: the pulse is held
    cb["on_session_end"](session_id="s", completed=True)
    assert cb["pre_verify"](session_id="s") is None and bus(home, "s")["state"] == "review"
    assert cb["pre_verify"]() is None
    r = rt(home, clock)
    r.store.ensure = lambda *a, **k: 1 / 0
    assert r.callbacks()["pre_verify"](session_id="s") is None


def test_every_subscribed_hook_has_a_callback_and_stream_hooks_are_absent(home, clock):
    cb = rt(home, clock).callbacks()
    assert set(cb) == set(H.SUBSCRIBED)
    assert len(H.SUBSCRIBED) == 12 and {"post_llm_call", "pre_verify"} <= set(H.SUBSCRIBED)
    assert not [h for h in cb if h.startswith("on_stream")]


class FakeCtx:
    def __init__(self):
        self.registered = {}

    def register_hook(self, name, cb):
        self.registered[name] = cb


def test_register_hooks_skips_unavailable_hooks_and_records_them(home, clock):
    ctx = FakeCtx()
    valid = set(H.SUBSCRIBED) - {"pre_verify", "pre_approval_request"}
    status = E.register_hooks(ctx, valid_hooks=valid, runtime=rt(home, clock))
    assert set(ctx.registered) == valid
    assert status["unavailable"] == ["pre_approval_request", "pre_verify"]
    on_disk = json.loads((P.cuttlefish_dir(home) / "hooks.json").read_text())
    assert on_disk["unavailable"] == ["pre_approval_request", "pre_verify"]
    assert on_disk["registered"] == sorted(valid)


def test_hooks_status_exposes_the_tool_signal_capability_for_doctor(home, clock):
    E.register_hooks(FakeCtx(), valid_hooks=set(H.SUBSCRIBED), runtime=rt(home, clock))
    on_disk = json.loads((P.cuttlefish_dir(home) / "hooks.json").read_text())
    assert on_disk["schema"] == "cf2909.hooks/2"
    assert on_disk["tool_signal"] == {"tui": True, "desktop": True}   # CONTRACT §2: a False host maps busy -> thinking


def test_register_hooks_with_a_full_core_registers_all_twelve(home, clock):
    ctx = FakeCtx()
    status = E.register_hooks(ctx, valid_hooks=set(H.SUBSCRIBED) | {"on_stream_delta"}, runtime=rt(home, clock))
    assert len(ctx.registered) == 12 and status["unavailable"] == []


def test_root_entry_registers_the_python_half_and_matches_the_manifest(home, monkeypatch):
    import pathlib
    import yaml
    import cuttlefish_theme
    ctx = FakeCtx()
    cuttlefish_theme.register(ctx)
    manifest = yaml.safe_load((pathlib.Path(cuttlefish_theme.__file__).parent / "plugin.yaml").read_text())
    assert manifest["name"] == "cuttlefish-theme" and str(manifest["version"]) == "0.22.0"
    assert set(manifest["provides_hooks"]) == set(ctx.registered) == set(H.SUBSCRIBED)
    assert not [h for h in manifest["provides_hooks"] if h.startswith("on_stream")]
    assert ctx.registered["pre_verify"]() is None
