#!/usr/bin/env python3
"""Deterministic mock OpenAI-compatible model for real-Desktop captures (dev only, never shipped).

Free, private and reproducible, so a capture never depends on a GPU box or a paid API. The behaviour is chosen by a tag
in the LAST user message:
  [work]     open the stream, say one short line, then send empty keep-alive chunks for CF_MOCK_WORK_S seconds
             (default 600): the session stays "working" without the transcript growing
  [brief]    stream for CF_MOCK_BRIEF_S seconds (default 6), then finish (switch away first: "finished unseen")
  [approve]  call the terminal tool with a command Hermes must ask approval for: the session "needs you"
  [fail]     HTTP 400 invalid_request_error (non-retryable): the turn ends in "error"
  [done]     answer at once (switch away first and the session is "finished unseen")
  anything else: a one-line answer.
After a tool result arrives, it answers in one line.
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WORK_S = float(os.environ.get("CF_MOCK_WORK_S", "600"))
BRIEF_S = float(os.environ.get("CF_MOCK_BRIEF_S", "6"))
DANGEROUS = "rm -rf /tmp/cuttlefish-demo-target"


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            return c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def _chunk(model: str, delta: dict, finish: str | None = None) -> bytes:
    body = {"id": "cf-mock", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D401 - quiet
        sys.stderr.write("mock: " + fmt % args + "\n")

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            return self._json(200, {"object": "list", "data": [{"id": "cf-mock", "object": "model", "owned_by": "cf"}]})
        return self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        model = req.get("model", "cf-mock")
        msgs = req.get("messages", [])
        text = _last_user(msgs)
        after_tool = bool(msgs) and msgs[-1].get("role") == "tool"
        if "[fail]" in text and not after_tool:
            return self._json(400, {"error": {"message": "mock: deliberately invalid request", "type": "invalid_request_error",
                                              "code": "invalid_request"}})
        if "[approve]" in text and not after_tool:
            call = {"index": 0, "id": "call_cf_1", "type": "function",
                    "function": {"name": "terminal", "arguments": json.dumps({"command": DANGEROUS})}}
            return self._reply(model, req, tool_call=call)
        if "[work]" in text and not after_tool:
            return self._reply(model, req, slow=WORK_S)
        if "[brief]" in text and not after_tool:
            return self._reply(model, req, content="Finished.", slow=BRIEF_S)
        return self._reply(model, req, content="Done." if after_tool else "Here you go.")

    def _reply(self, model, req, content="", tool_call=None, slow=0.0):
        if not req.get("stream"):
            msg = {"role": "assistant", "content": content or None}
            if tool_call:
                msg["tool_calls"] = [{k: v for k, v in tool_call.items() if k != "index"}]
            return self._json(200, {"id": "cf-mock", "object": "chat.completion", "created": int(time.time()), "model": model,
                                    "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if tool_call else "stop"}],
                                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(_chunk(model, {"role": "assistant"}))
            if tool_call:
                self.wfile.write(_chunk(model, {"tool_calls": [tool_call]}))
                self.wfile.write(_chunk(model, {}, "tool_calls"))
            elif slow:
                self.wfile.write(_chunk(model, {"content": content or "Working on it."}))
                end = time.time() + slow
                while time.time() < end:
                    self.wfile.write(_chunk(model, {"content": ""}))
                    self.wfile.flush()
                    time.sleep(1.0)
                self.wfile.write(_chunk(model, {}, "stop"))
            else:
                self.wfile.write(_chunk(model, {"content": content}))
                self.wfile.write(_chunk(model, {}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18931
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
