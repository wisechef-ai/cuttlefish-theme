"""Cuttlefish's dashboard API: ``GET /config`` (live) and ``GET /health``.

The web server loads this file via ``spec_from_file_location`` with no package
context (web_server_dashboard.py), so ``cuttlefish/liveconfig.py`` is loaded the
same way — by path, executed in place. ``/config`` re-reads ``config.yaml`` on
EVERY request: settings apply without a restart (SPEC C5). The desktop half
polls it only when the file's mtime moved.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

# Not resolve(): the mutator's worker overlays symlink this file, and resolving
# would follow the link back to the original tree instead of the worker's copy.
_ROOT = Path(__file__).parent.parent
_LIVECONFIG: Any = None

router = APIRouter()


def _live() -> Any:
    """The liveconfig module, importable however this file was loaded."""
    global _LIVECONFIG
    if _LIVECONFIG is None:
        spec = importlib.util.spec_from_file_location(
            "cuttlefish_liveconfig_by_path", _ROOT / "cuttlefish" / "liveconfig.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _LIVECONFIG = module
    return _LIVECONFIG


def _rev(payload: dict[str, Any]) -> str:
    """A content revision of what we serve: it moves exactly when the answer does."""
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@router.get("/config")
def get_config() -> dict[str, Any]:
    """The resolved settings + warnings, re-read from config.yaml per request."""
    settings, warnings = _live().resolve_live()
    return {"settings": settings, "warnings": warnings, "rev": _rev({"settings": settings, "warnings": warnings})}


@router.get("/health")
def get_health() -> dict[str, Any]:
    """Alive, and which plugin version this backend is."""
    return {"ok": True, "version": _live().plugin_version()}
