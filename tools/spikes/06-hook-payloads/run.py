#!/usr/bin/env python
"""Spike 06: drive real TUI turns against a temp HERMES_HOME with the hookdump plugin.
Usage: run.py OUTDIR [main|error|both]
Outputs: OUTDIR/main.jsonl, OUTDIR/error.jsonl (hook payloads + @@MARK rows), OUTDIR/screens/*.txt"""
import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import *  # noqa
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cf06-out-")
os.makedirs(f"{out}/screens", exist_ok=True)


def snap(t, name):
    open(f"{out}/screens/{name}.txt", "w").write(t.text())


def mark(dump, label):
    with open(dump, "a") as f:
        f.write(json.dumps({"hook": "@@MARK", "label": label, "ts": round(time.time(), 3)}) + "\n")
    print("MARK", label, flush=True)


def run_main():
    h = make_home(extra_cfg="approvals:\n  mode: manual\n")
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    dump = f"{out}/main.jsonl"
    print("HOME", h, flush=True)
    t = Tui(h, "a", HOOKDUMP_FILE=dump)
    assert boot(t), "boot failed"
    snap(t, "00-boot"); mark(dump, "booted")
    mark(dump, "plain-turn"); t.line("Reply with exactly: pong"); wait_idle(t); snap(t, "01-plain")
    mark(dump, "tool-call")
    t.line("Use the terminal tool to run: echo cf2909-tool-ok . Then say done."); wait_idle(t); snap(t, "02-tool")
    mark(dump, "clarify-asked")
    t.line("Use the clarify tool to ask me: 'Which colour?' with choices red and blue. Do nothing else until I answer.")
    t.wait_for(r"Which colour", 120); t.pump(3); snap(t, "03-clarify-open"); mark(dump, "clarify-open-observed")
    time.sleep(8); mark(dump, "clarify-still-open-8s")
    t.send("\r"); mark(dump, "clarify-answered(enter)"); wait_idle(t); snap(t, "04-clarify-answered")
    mark(dump, "clarify2-asked")
    t.line("Use the clarify tool again to ask me: 'Which fruit?' with choices apple and pear.")
    t.wait_for(r"Which fruit", 120); t.pump(3); snap(t, "05-clarify2-open")
    time.sleep(5); mark(dump, "clarify2-ctrl-c"); t.send("\x03"); t.pump(6); snap(t, "06-clarify2-interrupted")
    wait_idle(t, 60)
    mark(dump, "approval-asked")
    t.line("Use the terminal tool to run exactly: rm -rf /tmp/cf2909-approval-probe-dir")
    t.wait_for(r"(?i)approv|dangerous|deny", 120); t.pump(3); snap(t, "07-approval-open")
    time.sleep(5); mark(dump, "approval-deny"); t.send("d"); t.pump(2); t.send("\r")
    wait_idle(t, 90); snap(t, "08-approval-after")
    mark(dump, "compress"); t.line("/compress"); t.pump(20); wait_idle(t, 180); snap(t, "09-compress")
    mark(dump, "post-compress-turn"); t.line("Reply with exactly: after"); wait_idle(t); snap(t, "10-post-compress")
    mark(dump, "exit"); t.line("/exit"); t.pump(6); snap(t, "11-exit")
    t.p.terminate(force=True)
    return h


def run_error():
    h = make_home()
    cfg = open(f"{h}/config.yaml").read().replace(QWEN, "http://127.0.0.1:9/v1")
    open(f"{h}/config.yaml", "w").write(cfg)
    enable_plugin(h, "hookdump", f"{HERE}/hookdump")
    dump = f"{out}/error.jsonl"
    t = Tui(h, "e", HOOKDUMP_FILE=dump)
    assert boot(t), "boot failed (error home)"
    mark(dump, "error-turn"); t.line("hello"); t.pump(90); snap(t, "20-error")
    mark(dump, "error-end"); t.line("/exit"); t.pump(4); t.p.terminate(force=True)
    return h


if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "both"
    print("OUT", out, flush=True)
    if which in ("both", "main"):
        print("main home", run_main(), flush=True)
    if which in ("both", "error"):
        print("error home", run_error(), flush=True)
    print("DONE", flush=True)
