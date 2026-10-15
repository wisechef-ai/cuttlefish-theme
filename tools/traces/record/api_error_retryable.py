#!/usr/bin/env python3
"""Record `api-error-retryable`: dead base_url; api_request_error once per retry attempt, the turn never ends (<= 90 s).
   python3 tools/traces/record/api_error_retryable.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "dead base_url 127.0.0.1:9: api_request_error(retryable true) per attempt with backoff; no turn-end hook; /exit interrupts"

if __name__ == "__main__":
    with Recording("api-error-retryable", notes=NOTES, base_urls={"A": "http://127.0.0.1:9/v1"}) as rec:
        t = rec.open_tui("A")
        t0 = time.time()
        t.line("hello")
        assert t.wait_hook("api_request_error", n=1, timeout=120), "no api_request_error"
        t.pump(max(0, 80 - (time.time() - t0)))
        rec.exit_tui(t)
