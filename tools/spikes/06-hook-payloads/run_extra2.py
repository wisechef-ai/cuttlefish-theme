#!/usr/bin/env python
"""Spike 06c: (1) pre_verify reachability (edit a file via write_file), (2) approval DENY answered by quick-pick 4,
(3) NON-retryable API error (local stub returns HTTP 401) -> does the turn end with failed=True?
Usage: run_extra2.py OUTDIR"""
import sys, os, time, json, threading, http.server
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import *  # noqa
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1]; os.makedirs(f"{out}/screens", exist_ok=True)

def snap(t, n): open(f"{out}/screens/{n}.txt", "w").write(t.text())
def mark(d, l): open(d, "a").write(json.dumps({"hook": "@@MARK", "label": l, "ts": round(time.time(), 3)}) + "\n"); print("MARK", l, flush=True)

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        b = json.dumps({"error": {"message": "invalid api key (stub)", "type": "invalid_request_error", "code": "invalid_api_key"}}).encode()
        self.send_response(401); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    do_GET = do_POST
    def log_message(self, *a): pass

def verify_and_approval():
    h = make_home(extra_cfg="approvals:\n  mode: manual\n")
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    d = f"{out}/verify_approval.jsonl"
    t = Tui(h, "v", HOOKDUMP_FILE=d); assert boot(t)
    mark(d, "write-file-turn")
    t.line(f"Use the write_file tool to create {h}/hello.py containing a python hello world, then tell me it is done.")
    wait_idle(t, 240); snap(t, "50-write")
    mark(d, "approval-asked")
    t.line("Use the terminal tool to run exactly this command and nothing else: rm -rf /tmp/cf2909-approval-probe-dir")
    ok = t.wait_for(r"approval required", 240); mark(d, f"approval-visible={ok}"); t.pump(2); snap(t, "51-approval-open")
    time.sleep(4); mark(d, "approval-quickpick-4-deny"); t.send("4"); wait_idle(t, 120); snap(t, "52-approval-denied")
    t.line("/exit"); t.pump(4); t.p.terminate(force=True); return h

def failed_turn():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = make_home()
    cfg = open(f"{h}/config.yaml").read().replace(QWEN, f"http://127.0.0.1:{port}/v1")  # read BEFORE truncating
    open(f"{h}/config.yaml", "w").write(cfg)
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    d = f"{out}/failed.jsonl"
    t = Tui(h, "f", HOOKDUMP_FILE=d); assert boot(t)
    mark(d, "401-turn"); t.line("hello"); t.pump(45); snap(t, "60-401"); mark(d, "401-after-45s")
    t.line("Reply with exactly: again"); t.pump(30); snap(t, "61-401-second")
    mark(d, "exit"); t.line("/exit"); t.pump(4); t.p.terminate(force=True); return h

if len(sys.argv) < 3 or sys.argv[2] != "failed-only":
    print("verify/approval", verify_and_approval(), flush=True)
print("failed", failed_turn(), flush=True)
print("DONE")
