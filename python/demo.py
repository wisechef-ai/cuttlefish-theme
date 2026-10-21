"""``hermes cuttlefish demo [--seconds N]``: walks the reserved lineage ``cuttlefish-demo`` through every state by
writing REAL bus entries (``source: "demo"``, live heartbeat), so any surface that is watching shows them.

It touches only its own lineage: its bus file and its identity record are removed on exit, including on SIGINT /
SIGTERM / SIGHUP. Other sessions' entries are never read for writing."""
import os
import signal
import time

from . import bus, identity_store, paths
from .domain import reducer

ROOT = "cuttlefish-demo"
SOURCE = "demo"
# (label, hook events). The reducer decides what state results: nothing here names a state, so the demo stays
# honest when the state vocabulary changes (thinking | tool).
SCRIPT = (
    ("idle", [("on_session_reset", {})]),
    ("a turn starts", [("pre_llm_call", {})]),
    ("a tool runs", [("pre_tool_call", {"tool_name": "terminal", "tool_call_id": "demo-1"})]),
    ("the tool returns", [("post_tool_call", {"tool_name": "terminal", "tool_call_id": "demo-1"})]),
    ("the turn ends, then a verify pass", [("on_session_end", {"completed": True}), ("pre_verify", {})]),
    ("settled", [("on_session_end", {"completed": True})]),
    ("an approval is needed", [("pre_llm_call", {}), ("pre_approval_request", {"tool_call_id": "demo-2"})]),
    ("you answer", [("post_approval_response", {"tool_call_id": "demo-2"})]),
    ("an API error", [("api_request_error", {})]),
    ("recovered", [("pre_llm_call", {}), ("on_session_end", {"completed": True})]),
)


def run(home, *, seconds=0.0, out=print, clock=time.time, sleep=time.sleep, pid=None, host=None):
    total = seconds if seconds and seconds > 0 else 20.0
    per = total / len(SCRIPT)
    writer = bus.BusWriter(home, clock=clock, pid=pid, host=host)
    store = identity_store.IdentityStore(home, clock=clock)
    prev = {}

    def _stop(signum, _frame):
        raise KeyboardInterrupt

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)):
            if sig is not None:
                prev[sig] = signal.signal(sig, _stop)
    except ValueError:  # not the main thread (tests): the finally block still cleans up
        prev = {}
    try:
        ident = store.ensure(ROOT, live_roots=lambda: bus.live_roots(home, now=clock(), this_host=writer.host,
                                                                      pid_alive=bus.pid_alive))
        out("cuttlefish demo: lineage %r, hue %.2f deg, %.1fs per step. Ctrl-C stops and cleans up."
            % (ROOT, ident.hue_deg, per))
        writer.start_heartbeat()
        for label, events in SCRIPT:
            for kind, payload in events:
                entry = writer.record(ROOT, ROOT, {"t": clock(), "kind": kind, "session_id": ROOT, "payload": payload})
            entry["source"] = SOURCE  # same dict the heartbeat re-publishes
            bus.atomic_write_json(paths.bus_file(home, ROOT), entry)
            out("  %-34s -> %s" % (label, entry["state"]))
            sleep(per)
        out("demo finished.")
        return 0
    except KeyboardInterrupt:
        out("demo interrupted.")
        return 130
    finally:
        writer.stop()
        try:
            os.unlink(paths.bus_file(home, ROOT))
        except OSError:
            pass
        store.forget(ROOT)
        for sig, handler in prev.items():
            signal.signal(sig, handler)
