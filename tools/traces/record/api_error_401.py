#!/usr/bin/env python3
"""Record `api-error-401`: a local stub answers HTTP 401. api_request_error fires once, no turn-end hook ever follows.
   python3 tools/traces/record/api_error_401.py"""
import http.server
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "stub provider returns HTTP 401: api_request_error(status_code 401, retryable false) once per turn; no on_session_end/post_llm_call; second turn errors again"


class Stub(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.dumps({"error": {"message": "invalid credentials (stub)", "type": "invalid_request_error", "code": "invalid_credentials"}}).encode()
        self.send_response(401)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    with Recording("api-error-401", notes=NOTES, base_urls={"A": url}) as rec:
        t = rec.open_tui("A")
        t.line("hello")
        assert t.wait_hook("api_request_error", n=1, timeout=120), "no api_request_error #1"
        t.pump(25)                      # long enough to prove nothing terminates the fault
        t.line("Reply with exactly: again")
        assert t.wait_hook("api_request_error", n=2, timeout=120), "no api_request_error #2"
        t.pump(10)
        rec.exit_tui(t)
    srv.shutdown()
