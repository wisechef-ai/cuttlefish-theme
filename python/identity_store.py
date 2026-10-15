"""``identity.json`` (CONTRACT §1/§4): allocate on the first hook for an unknown lineage root, then never again."""
import os
import sqlite3
import threading
from collections import namedtuple
from contextlib import contextmanager

try:  # POSIX advisory lock; absent on Windows, where we fall back to the atomic replace alone
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from . import bus, paths
from .domain import allocator

SCHEMA = "cf2909.identity/1"
HOP_CAP = 32
MAX_ENTRIES = 512
MAX_AGE_S = 30 * 86400
TOUCH_EVERY_S = 60

Identity = namedtuple("Identity", "lineage_root hue_cd hue_deg name allocated")


class IdentityStore:
    def __init__(self, home, *, clock):
        self.home = home
        self.clock = clock
        self._mu = threading.Lock()
        self._cache = {}  # lineage root -> entry dict (as last read/written)
        self._lineage = {}  # session id -> lineage root
        self._touched = {}  # lineage root -> ts of last write by this process

    # -- state.db (read-only) -------------------------------------------------------------------
    def _db(self):
        p = os.path.join(str(self.home), "state.db")
        if not os.path.exists(p):
            return None
        try:
            from urllib.parse import quote
            return sqlite3.connect("file:%s?mode=ro" % quote(p), uri=True, timeout=0.25)
        except sqlite3.Error:
            return None

    def lineage_root(self, session_id):
        """Walk sessions.parent_session_id (<= 32 hops). Missing db/table/row: the id itself."""
        if session_id in self._lineage:
            return self._lineage[session_id]
        cur, seen = session_id, {session_id}
        con = self._db()
        if con is not None:
            try:
                for _ in range(HOP_CAP):
                    row = con.execute("select parent_session_id from sessions where id=?", (cur,)).fetchone()
                    parent = row[0] if row else None
                    if not isinstance(parent, str) or not parent or parent in seen:
                        break
                    cur = parent
                    seen.add(cur)
            except sqlite3.Error:
                pass
            finally:
                con.close()
        self._lineage[session_id] = cur
        return cur

    def _title(self, root):
        con = self._db()
        if con is None:
            return ""
        try:
            row = con.execute("select title from sessions where id=?", (root,)).fetchone()
            return allocator.trim_name(row[0]) if row and isinstance(row[0], str) else ""
        except sqlite3.Error:
            return ""
        finally:
            con.close()

    # -- file ---------------------------------------------------------------------------------
    @contextmanager
    def _file_lock(self):
        d = paths.cuttlefish_dir(self.home)
        os.makedirs(d, exist_ok=True)
        if fcntl is None:  # pragma: no cover
            yield
            return
        with open(paths.identity_lock(self.home), "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def _read(self):
        doc = bus.read_json(paths.identity_file(self.home))
        if not isinstance(doc, dict) or not isinstance(doc.get("sessions"), dict):
            doc = {"schema": SCHEMA, "rev": 0, "sessions": {}}
        doc["schema"] = SCHEMA
        if not isinstance(doc.get("rev"), int):
            doc["rev"] = 0
        return doc

    def _write(self, doc):
        doc["rev"] += 1
        bus.atomic_write_json(paths.identity_file(self.home), doc)

    @staticmethod
    def _ident(root, e, allocated):
        return Identity(root, e["hue_cd"], e["hue_deg"], e["name"], allocated)

    # -- API ----------------------------------------------------------------------------------
    def ensure(self, session_id, *, live_roots):
        """Identity for the lineage of ``session_id``; allocates (once, ever) if the root is unknown.
        ``live_roots`` is a callable returning the lineage roots whose bus entry is live (the peers)."""
        root = self.lineage_root(session_id)
        now = self.clock()
        with self._mu:
            e = self._cache.get(root)
            if e is not None and now - self._touched.get(root, 0) < TOUCH_EVERY_S:
                return self._ident(root, e, False)
            with self._file_lock():
                doc = self._read()
                e = doc["sessions"].get(root)
                allocated = e is None
                if allocated:
                    peers = [doc["sessions"][r]["hue_cd"] for r in live_roots()
                             if r != root and isinstance(doc["sessions"].get(r), dict)
                             and isinstance(doc["sessions"][r].get("hue_cd"), int)]
                    a = allocator.allocate(root, peers)
                    e = {"hue_cd": a.hue_cd, "hue_deg": a.hue_cd / 100,
                         "name": self._title(root) or allocator.default_name(root),
                         "allocated_at": now, "last_seen": now}
                    doc["sessions"][root] = e
                else:
                    if e.get("name") == allocator.default_name(root):  # label upgrades once a title exists
                        t = self._title(root)
                        if t:
                            e["name"] = t
                    e["last_seen"] = now
                if len(doc["sessions"]) > MAX_ENTRIES:
                    self._sweep_doc(doc, now)
                self._write(doc)
            self._cache[root] = e
            self._touched[root] = now
            return self._ident(root, e, allocated)

    @staticmethod
    def _sweep_doc(doc, now):
        s = doc["sessions"]
        for r in [r for r, e in s.items() if now - e.get("last_seen", 0) > MAX_AGE_S]:
            del s[r]
        if len(s) > MAX_ENTRIES:
            for r in sorted(s, key=lambda r: s[r].get("last_seen", 0))[: len(s) - MAX_ENTRIES]:
                del s[r]

    def sweep(self):
        """Drop entries unseen for 30 days; keep at most 512 (oldest last_seen first)."""
        now = self.clock()
        with self._mu, self._file_lock():
            doc = self._read()
            before = len(doc["sessions"])
            self._sweep_doc(doc, now)
            if len(doc["sessions"]) != before:
                self._write(doc)
            self._cache = {r: e for r, e in self._cache.items() if r in doc["sessions"]}
