"""``bus/<lineage_root>.json`` (CONTRACT §5): atomic writes, monotonic seq, journal <= 32, heartbeat."""
import json
import logging
import os
import socket
import tempfile
import threading
import time
import weakref

from . import paths
from .domain import reducer, resolve

log = logging.getLogger("cuttlefish")

SCHEMA = "cf2909.bus/2"
JOURNAL_MAX = 32
SWEEP_FILES = 64
SWEEP_AGE_S = 24 * 3600


def atomic_write_json(path, obj):
    """tmp file in the same directory + os.replace: a reader sees the old or the new file, never half."""
    path = os.fspath(path)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_entries(home):
    """{lineage_root: entry} for every readable bus file."""
    out = {}
    d = paths.bus_dir(home)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json") or n.startswith(".tmp-"):
            continue
        e = read_json(d / n)
        if isinstance(e, dict):
            out[e.get("lineage_root") if isinstance(e.get("lineage_root"), str) else n[:-5]] = e
    return out


def live_roots(home, *, now, this_host, pid_alive):
    """Lineage roots whose entry resolves to a live (non-unknown) state: the allocator's peers."""
    return {r for r, e in read_entries(home).items()
            if resolve.resolve_entry(e, now=now, this_host=this_host, pid_alive=pid_alive) != "unknown"}


def sweep(home, now, limit=SWEEP_FILES):
    """Delete bus files whose heartbeat is older than 24 h. Examines at most ``limit`` files, oldest
    first. Returns how many were deleted."""
    d = paths.bus_dir(home)
    try:
        files = [(e.stat().st_mtime_ns, e.path) for e in os.scandir(d)
                 if e.name.endswith(".json") and not e.name.startswith(".tmp-")]
    except OSError:
        return 0
    files.sort()
    removed = 0
    for mtime_ns, p in files[:limit]:
        e = read_json(p)
        hb = e.get("heartbeat") if isinstance(e, dict) else None
        age = now - hb if isinstance(hb, (int, float)) and not isinstance(hb, bool) else now - mtime_ns / 1e9
        if age > SWEEP_AGE_S:
            try:
                os.unlink(p)
                removed += 1
            except OSError:
                pass
    return removed


class _Slot:
    __slots__ = ("durable_id", "model", "state", "since", "seq", "journal", "source", "entry")

    def __init__(self):
        self.durable_id = ""
        self.model = reducer.initial()
        self.state = "idle"
        self.since = None
        self.seq = 0
        self.journal = []
        self.source = ""
        self.entry = None


def _hb_loop(ref, stop, interval):
    while not stop.wait(interval):
        w = ref()
        if w is None:
            return
        try:
            w.refresh_heartbeats()
        except Exception as e:  # never let the daemon die or spam
            log.debug("cuttlefish heartbeat: %r", e)
        del w


class BusWriter:
    def __init__(self, home, *, clock=time.time, pid=None, host=None, heartbeat_interval=5.0):
        self.home = home
        self.clock = clock
        self.pid = os.getpid() if pid is None else pid
        self.host = host if host is not None else socket.gethostname()
        self.interval = heartbeat_interval
        self._lock = threading.RLock()
        self._slots = {}
        self._thread = None
        self._thread_pid = None
        self._stop = threading.Event()

    # -- state ---------------------------------------------------------------------------------
    def _load(self, root):
        slot = _Slot()
        e = read_json(paths.bus_file(self.home, root))
        if isinstance(e, dict) and isinstance(e.get("journal"), list) and isinstance(e.get("seq"), int):
            try:
                model = reducer.initial()
                for j in e["journal"]:
                    model = reducer.reduce(model, j)
                slot.model, slot.seq, slot.journal = model, e["seq"], e["journal"][-JOURNAL_MAX:]
                last = e["journal"][-1]["t"] if e["journal"] else 0
                old = e.get("state")                    # a cf2909.bus/1 file says `working`: re-resolve it (thinking | tool)
                slot.state = old if old and old != "working" else resolve.resolve(model, last)
                slot.since = e.get("since")
            except Exception:
                slot = _Slot()
        return slot

    def record(self, durable_id, root, event):
        """Apply one normalised event for ``root`` and publish. Returns the entry dict."""
        with self._lock:
            slot = self._slots.get(root)
            if slot is None:
                slot = self._slots[root] = self._load(root)
            slot.model = reducer.reduce(slot.model, event)
            state = resolve.resolve(slot.model, event["t"])
            if state != slot.state or slot.since is None:
                slot.since = event["t"]
            slot.state = state
            slot.journal = (slot.journal + [event])[-JOURNAL_MAX:]
            slot.seq += 1
            slot.durable_id, slot.source = durable_id, event["kind"]
            slot.entry = {
                "schema": SCHEMA, "profile_home": str(self.home), "durable_id": durable_id,
                "lineage_root": root, "owner_pid": self.pid, "owner_host": self.host, "seq": slot.seq,
                "state": slot.state, "since": slot.since, "source": slot.source,
                "review_until": slot.model["review_until"],
                "heartbeat": self.clock(), "journal": slot.journal,
            }
            target = paths.bus_file(self.home, root)
            if slot.state == "unknown":  # finalized: a missing file already resolves to unknown
                try:
                    os.unlink(target)
                except OSError:
                    pass
            else:
                atomic_write_json(target, slot.entry)
            return slot.entry

    def refresh_heartbeats(self):
        with self._lock:
            now = self.clock()
            for root, slot in self._slots.items():
                if slot.entry is None or slot.state == "unknown":
                    continue
                slot.entry = dict(slot.entry, heartbeat=now)
                atomic_write_json(paths.bus_file(self.home, root), slot.entry)

    # -- heartbeat daemon ----------------------------------------------------------------------
    def start_heartbeat(self):
        """Idempotent and non-blocking. One daemon thread per writer (the runtime owns one per process);
        restarted if the process forked."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._thread_pid == os.getpid():
                return
            self._stop = threading.Event()
            t = threading.Thread(target=_hb_loop, args=(weakref.ref(self), self._stop, self.interval),
                                 name="cuttlefish-heartbeat", daemon=True)
            self._thread, self._thread_pid = t, os.getpid()
            t.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2)
