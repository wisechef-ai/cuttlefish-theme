"""Hook callbacks. Each is wrapped: an exception is logged once and NEVER reaches the agent turn."""
import logging
import socket
import time
from pathlib import Path

from . import bus, identity_store, paths
from .domain import reducer

log = logging.getLogger("cuttlefish")

# CONTRACT §2 table hooks == spike 06 subscribe list (+ the optional post_llm_call / pre_verify observers).
# Never on_stream_*: delta is high-rate and the state bus must not sit on the token path.
SUBSCRIBED = (
    "on_session_reset", "on_session_start", "pre_llm_call", "post_llm_call", "pre_verify",
    "on_session_end", "on_session_finalize", "pre_tool_call", "post_tool_call",
    "pre_approval_request", "post_approval_response", "api_request_error",
)
_TOOL_HOOKS = ("pre_tool_call", "post_tool_call")


class Runtime:
    def __init__(self, home=None, *, clock=time.time, pid=None, host=None, pid_alive=None,
                 heartbeat_interval=5.0):
        self.home = Path(home) if home else paths.hermes_home()
        self.clock = clock
        self.host = host if host is not None else socket.gethostname()
        self.pid_alive = pid_alive or bus.pid_alive
        self.store = identity_store.IdentityStore(self.home, clock=clock)
        self.bus = bus.BusWriter(self.home, clock=clock, pid=pid, host=self.host,
                                 heartbeat_interval=heartbeat_interval)
        self._logged = set()

    def handle(self, hook, kwargs):
        ts = self.clock()
        ev = reducer.normalise(hook, kwargs, ts)
        sid = ev["session_id"]
        if not sid:  # auxiliary hooks (compression) carry an empty id
            return
        if hook in _TOOL_HOOKS and ev["tool_name"] != "clarify":  # hot path: only clarify matters
            return
        ident = self.store.ensure(sid, live_roots=lambda: bus.live_roots(
            self.home, now=ts, this_host=self.host, pid_alive=self.pid_alive))
        self.bus.record(sid, ident.lineage_root, ev)
        self.bus.start_heartbeat()
        if hook == "on_session_finalize":
            bus.sweep(self.home, ts)
            self.store.sweep()

    def _log_once(self, hook, exc):
        key = (type(exc).__name__, str(exc))
        if key not in self._logged:
            self._logged.add(key)
            log.warning("cuttlefish-theme: hook %s failed (further identical failures are silent): %r", hook, exc)

    def callbacks(self):
        def make(hook):
            def cb(*args, **kwargs):
                try:
                    self.handle(hook, kwargs)
                except Exception as e:  # noqa: BLE001 - nothing may escape into the agent turn
                    try:
                        self._log_once(hook, e)
                    except Exception:
                        pass
                return None  # pre_verify can veto/continue on non-None: always None

            cb.__name__ = "cuttlefish_" + hook
            return cb

        return {h: make(h) for h in SUBSCRIBED}
