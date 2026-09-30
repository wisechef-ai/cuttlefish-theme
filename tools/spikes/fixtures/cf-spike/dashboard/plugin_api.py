"""cf-spike backend, mounted at /api/plugins/cf-spike/ (spike 08).

/ping answers WHICH backend served the call (pid, HERMES_HOME, port hint), so a
receipt can prove local vs remote routing from the response body alone.
/events is a WebSocket that pushes a tick per second (ctx.socket probe).
"""
from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, WebSocket

router = APIRouter()
_BOOT = time.time()


@router.get("/ping")
def ping():
    return {
        "plugin": "cf-spike",
        "pid": os.getpid(),
        "hermes_home": os.environ.get("HERMES_HOME", ""),
        "marker": os.environ.get("CF_SPIKE_BACKEND_MARKER", ""),
        "uptime_s": round(time.time() - _BOOT, 3),
        "t": time.time(),
    }


@router.websocket("/events")
async def events(ws: WebSocket):
    await ws.accept()
    n = 0
    try:
        while True:
            n += 1
            await ws.send_json({"tick": n, "pid": os.getpid(), "t": time.time()})
            await asyncio.sleep(1)
    except Exception:
        return
