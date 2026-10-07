"""On-disk raw-answer cache for G5 so a crashed or rate-limited run resumes without re-spending.

Key = sha256 over (backend, model, image sha256, prompt sha256). Only successful raw answers are stored; transport
errors never are. ``--no-cache`` makes a Cache with enabled=False (no reads, no writes).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("G5_CACHE_DIR", "") or Path(__file__).resolve().parent / ".g5_cache")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def key(backend: str, model: str, png: Path, prompt: str) -> str:
    parts = [backend, model, _sha(Path(png).read_bytes()), _sha(prompt.encode())]
    return _sha("\x1f".join(parts).encode())


class Cache:
    def __init__(self, root: Path = DEFAULT_DIR, enabled: bool = True):
        self.root, self.enabled = Path(root), enabled

    def _path(self, k: str) -> Path:
        return self.root / k[:2] / f"{k}.json"

    def get(self, k: str):
        if not self.enabled:
            return None
        try:
            return json.loads(self._path(k).read_text())["raw"]
        except (OSError, ValueError, KeyError):
            return None

    def put(self, k: str, raw: str) -> None:
        if not self.enabled:
            return
        p = self._path(k)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent)
        with os.fdopen(fd, "w") as f:
            json.dump({"raw": raw}, f)
        os.replace(tmp, p)   # atomic: a crash never leaves a half-written entry


def cached(fn, backend: str, model: str, cache: Cache):
    """Wrap ``fn(png, prompt)``. ``wrapper.last_cached`` reports whether the calling thread's last answer came from disk."""
    tl = threading.local()

    def call(png, prompt):
        k = key(backend, model, png, prompt)
        hit = cache.get(k)
        if hit is not None:
            tl.cached = True
            return hit
        tl.cached = False
        raw = fn(png, prompt)
        cache.put(k, raw)
        return raw

    return CachedBackend(call, tl, getattr(fn, "retries_internal", False))


class CachedBackend:
    def __init__(self, call, tl, retries_internal: bool):
        self._call, self._tl, self.retries_internal = call, tl, retries_internal

    def __call__(self, png, prompt):
        return self._call(png, prompt)

    @property
    def last_cached(self) -> bool:
        return bool(getattr(self._tl, "cached", False))
