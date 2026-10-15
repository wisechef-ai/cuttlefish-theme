"""GET /identity and GET /state (CONTRACT §6). Read-only: this module never writes a file.

Core imports this file standalone (spec_from_file_location, no package), so the sibling ``python/``
package is loaded by path under a private name.
"""
import hashlib
import importlib
import importlib.util
import json
import socket
import sys
import time
from pathlib import Path

try:
    from fastapi import APIRouter
except ImportError:  # core always has fastapi; this keeps the module importable for plain-function tests
    APIRouter = None

_ROOT = Path(__file__).resolve().parent.parent
_PKG = "_cuttlefish_py_dashboard"


def _load():
    if _PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _PKG, _ROOT / "python" / "__init__.py", submodule_search_locations=[str(_ROOT / "python")])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = mod
        spec.loader.exec_module(mod)
    return (importlib.import_module(_PKG + ".paths"), importlib.import_module(_PKG + ".bus"),
            importlib.import_module(_PKG + ".domain.resolve"), importlib.import_module(_PKG + ".domain.allocator"))


_paths, _bus, _resolve, _alloc = _load()

_now = time.time
_host = socket.gethostname
_pid_alive = _bus.pid_alive


def _identity_doc():
    doc = _bus.read_json(_paths.identity_file(_paths.hermes_home()))
    if not isinstance(doc, dict) or not isinstance(doc.get("sessions"), dict):
        return {"schema": "cf2909.identity/1", "rev": 0, "sessions": {}}
    return doc


def identity():
    return dict(_identity_doc(), host=_host())


def state():
    home, now, host = _paths.hermes_home(), _now(), _host()
    ident = _identity_doc()["sessions"]
    sessions, sig = {}, {}
    for root, e in sorted(_bus.read_entries(home).items()):
        resolved = _resolve.resolve(e, now=now, this_host=host, pid_alive=_pid_alive)
        rec = ident.get(root) if isinstance(ident.get(root), dict) else {}
        since = e.get("since")
        alarm = int(now - since) if resolved == "needs-you" and isinstance(since, (int, float)) else None
        sessions[root] = {
            "state": resolved, "raw_state": e.get("state"), "since": since, "durable_id": e.get("durable_id"),
            "hue_deg": rec.get("hue_deg"), "name": rec.get("name") or _alloc.default_name(root),
            "alarm_age_s": alarm,
        }
        s = sessions[root]
        sig[root] = [s["state"], s["raw_state"], s["since"], s["durable_id"], s["hue_deg"], s["name"]]
    # rev changes only when content does: hash of everything except the clock-driven fields
    rev = int.from_bytes(hashlib.blake2b(json.dumps(sig, sort_keys=True).encode(), digest_size=6).digest(), "big")
    return {"schema": "cf2909.state-api/1", "rev": rev, "now": now, "sessions": sessions}


router = None
if APIRouter is not None:
    router = APIRouter()
    router.get("/identity")(identity)
    router.get("/state")(state)
