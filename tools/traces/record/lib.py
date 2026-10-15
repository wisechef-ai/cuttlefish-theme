"""Shared harness for the trace recorders: real `hermes --tui` (upstream node bundle) on throwaway HERMES_HOMEs.

A recorder script does:

    with Recording("turn") as rec:
        tui = rec.open_tui("A")
        rec.turn(tui, "Reply with exactly: pong")
    # leaving the block copies state.db, writes meta.json and converts to tools/traces/<name>.jsonl

Raw (unscrubbed: prompts, paths) recordings go to the vault, never into the repo:
  ~/obsidian-vault/projects/cuttlefish-theme/p2/traces-raw/<name>/
"""
import datetime
import fcntl
import json
import os
import pty
import re
import select
import shutil
import signal
import sqlite3
import struct
import subprocess
import tempfile
import termios
import threading
import time
from pathlib import Path

import pyte

HOME = os.environ.get("HOME", "/home/adam")
REPO = Path(__file__).resolve().parents[3]
UPSTREAM = Path(os.environ.get("CF_UPSTREAM", f"{HOME}/.worktrees/hermes-agent/cf2909-upstream"))
INSTALLED = Path(f"{HOME}/.hermes/hermes-agent")  # read-only: only its venv interpreter is borrowed (upstream has no venv)
PY = os.environ.get("CF_HERMES_PYTHON", str(INSTALLED / "venv" / "bin" / "python3"))
NODE = os.environ.get("CF_NODE", shutil.which("node") or "node")
RAW_ROOT = Path(os.environ.get("CF_TRACES_RAW", f"{HOME}/obsidian-vault/projects/cuttlefish-theme/p2/traces-raw"))
OUT_DIR = REPO / "tools" / "traces"
HOOKDUMP = REPO / "tools" / "spikes" / "06-hook-payloads" / "hookdump"
QWEN = "http://100.106.27.136:8000/v1"
MODEL = "custom:qwen38-local"
HEARTBEAT_S = 5.0
READY = re.compile(r"─ ready")


def runtime_sha():
    return subprocess.run(["git", "-C", str(UPSTREAM), "rev-parse", "--short=11", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def make_home(extra_cfg="", base_url=QWEN):
    home = tempfile.mkdtemp(prefix="cf2909-trace-home-")
    Path(home, "config.yaml").write_text(f"""model:
  default: qwen3.8-27b-heretic
  provider: qwen38-local
providers:
  qwen38-local:
    api: {base_url}
    api_mode: chat_completions
    key_env: QWEN38_API_KEY
    context_length: 1048576
    models:
      qwen3.8-27b-heretic:
        context_length: 1048576
display:
  interface: tui
{extra_cfg}
plugins:
  enabled:
    - hookdump
""")
    shutil.copytree(HOOKDUMP, f"{home}/plugins/hookdump")
    return home


class Tui:
    """One real TUI process (node bundle + its tui_gateway child) on a pty, with a liveness sampler thread."""

    def __init__(self, rec, label, home, cols=140, rows=40):
        self.rec, self.label, self.home = rec, label, home
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        fd, self.active_file = tempfile.mkstemp(prefix="hermes-tui-active-session-", suffix=".json", dir=rec.tmp)
        os.close(fd)  # empty, like main_tui_launch.py: the TUI writes {"session_id": ...} into it
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERMES_", "_HERMES", "TERMINAL_", "COGNEE", "AI_AGENT", "NO_COLOR", "PYTHON"))}
        env.update(HOME=HOME, HERMES_HOME=home, QWEN38_API_KEY="x", TERM="xterm-256color", COLORTERM="truecolor",
                   HERMES_PYTHON=PY, HERMES_PYTHON_SRC_ROOT=str(UPSTREAM), HERMES_CWD=rec.workspace, NODE_ENV="production",
                   HERMES_TUI_NATIVE="0", HERMES_TUI_ACTIVE_SESSION_FILE=self.active_file, HOOKDUMP_FILE=str(rec.raw / f"hooks-{label}.jsonl"),
                   NODE_OPTIONS="--max-old-space-size=4096", HERMES_DISABLE_LAZY_INSTALLS="1")
        cmd = [NODE, "--expose-gc", str(UPSTREAM / "ui-tui" / "dist" / "entry.js")]
        self.exit_status = None
        self.dead_emitted = False
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(rec.workspace)
            os.execvpe(cmd[0], cmd, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.stop = threading.Event()
        self.sampler = threading.Thread(target=self._sample, daemon=True)
        self.sampler.start()

    # ---- liveness (sampled by the recorder, not by the host: the heartbeat is the OWNER-alive proof the bus will give)
    def alive(self):
        if self.exit_status is not None:
            return False
        try:
            pid, st = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self.exit_status = -1
            return False
        if pid == 0:
            return True
        self.exit_status = st
        return False

    def bound_session(self):
        try:
            return json.loads(Path(self.active_file).read_text() or "{}").get("session_id")
        except (OSError, ValueError):
            return None

    def _emit(self, kind, **kw):
        self.rec.liveness(dict(profile=self.label, kind=kind, ts=round(time.time(), 3), **kw))

    def _emit_dead(self, sid):
        with self.rec._lock:
            if self.dead_emitted:
                return
            self.dead_emitted = True
        self._emit("pid_dead", session=sid or self.bound_session(), pid=self.pid)

    def _sample(self):
        last_bound, last_hb, last_sid = None, 0.0, None
        while not self.stop.is_set():
            now = time.time()
            alive = self.alive()
            sid = self.bound_session()
            bound = sid is not None
            sid = sid or last_sid
            if bound != last_bound and sid is not None:  # no id yet = nothing to attribute the line to
                self._emit("binding", session=sid, bound=bound)
                last_bound = bound
            last_sid = sid
            if not alive:
                self._emit_dead(sid)
                return
            if sid is not None and now - last_hb >= HEARTBEAT_S:
                self._emit("heartbeat", session=sid)
                last_hb = now
            time.sleep(0.5)

    # ---- pty
    def pump(self, secs=1.0):
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    d = os.read(self.fd, 65536)
                except OSError:
                    return False
                if not d:
                    return False
                self.stream.feed(d)
        return True

    def text(self):
        return "\n".join(l.rstrip() for l in self.screen.display).rstrip()

    def send(self, s):
        os.write(self.fd, s if isinstance(s, bytes) else s.encode())

    def line(self, s):
        self.send(s)
        time.sleep(0.3)
        self.send("\r")

    # ---- hook-log waits (deterministic; the screen is only a fallback)
    def hooks(self):
        p = self.rec.raw / f"hooks-{self.label}.jsonl"
        if not p.exists():
            return []
        out = []
        for l in p.read_text().splitlines():
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if r.get("env_active_file") == self.active_file:
                out.append(r)
        return out

    def count(self, hook, **ids):
        return sum(1 for r in self.hooks() if r["hook"] == hook and all(r["ids"].get(k) == v for k, v in ids.items()))

    def wait_hook(self, hook, n=1, timeout=240, **ids):
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.5)
            if self.count(hook, **ids) >= n:
                return True
            if not self.alive():
                return False
        return False

    def close(self, clean=True):
        self.stop.set()
        self.sampler.join(timeout=2)
        if self.alive():
            try:
                os.kill(self.pid, signal.SIGTERM)
                time.sleep(0.3)
                os.kill(self.pid, signal.SIGKILL)
            except OSError:
                pass
            self.alive()
        if not self.alive():
            self._emit_dead(None)
        if clean:
            Path(self.active_file).unlink(missing_ok=True)  # the launcher's epilogue unlinks the hint file on a clean exit


class Recording:
    def __init__(self, name, profiles=("A",), notes="", host="tui", base_urls=None, extra_cfg=None):
        self.name, self.profiles, self.notes, self.host = name, list(profiles), notes, host
        self.raw = RAW_ROOT / name
        shutil.rmtree(self.raw, ignore_errors=True)
        self.raw.mkdir(parents=True)
        self.tmp = tempfile.mkdtemp(prefix="cf2909-trace-tmp-")
        self.workspace = tempfile.mkdtemp(prefix="cf2909-trace-ws-")
        self.homes = {p: make_home((extra_cfg or {}).get(p, ""), (base_urls or {}).get(p, QWEN)) for p in self.profiles}
        self.tuis = []
        self._lv = self.raw / "liveness.jsonl"  # opened per write: a long-lived fd got stray bytes in a 5-way threaded run
        self._lock = threading.Lock()
        self.t0 = time.time()
        self.recorded_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def __enter__(self):
        return self

    def liveness(self, row):
        with self._lock, open(self._lv, "a") as f:
            f.write(json.dumps(row) + "\n")

    def open_tui(self, label, boot_timeout=900):
        t = Tui(self, label, self.homes[label])
        self.tuis.append(t)
        if not t.wait_hook("on_session_reset", timeout=boot_timeout):
            raise RuntimeError(f"{label}: TUI never created a session (screen: {t.text()[-400:]!r})")
        self.wait_ready(t)
        return t

    def wait_ready(self, t, timeout=300):
        end = time.time() + timeout
        while time.time() < end:
            t.pump(1.0)
            if READY.search(t.text()):
                return True
        return False

    def turn(self, t, text, timeout=300):
        """Send a user message and wait for its turn-end hook."""
        n = t.count("on_session_end")
        t.line(text)
        ok = t.wait_hook("on_session_end", n=n + 1, timeout=timeout)
        t.pump(1.0)
        return ok

    def settle(self, t, quiet=6.0, timeout=150):
        """Pump until this TUI's hook stream has been silent for `quiet` seconds."""
        last, since, end = len(t.hooks()), time.time(), time.time() + timeout
        while time.time() < end:
            t.pump(0.5)
            n = len(t.hooks())
            if n != last:
                last, since = n, time.time()
            elif time.time() - since >= quiet:
                return True
        return False

    def exit_tui(self, t, wait=15):
        t.line("/exit")
        end = time.time() + wait
        while time.time() < end and t.alive():
            t.pump(0.5)
        t.close(clean=not t.alive())

    def __exit__(self, et, ev, tb):
        for t in self.tuis:
            if t.alive():
                t.close(clean=False)
            else:
                t.stop.set()
        time.sleep(0.8)
        for p, home in self.homes.items():
            db = Path(home) / "state.db"
            if db.exists():
                src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                dst = sqlite3.connect(self.raw / f"state-{p}.db")
                src.backup(dst)
                dst.close()
                src.close()
        meta = dict(name=self.name, host=self.host, runtime="upstream", runtime_sha=runtime_sha(), recorded_at=self.recorded_at,
                    model=MODEL, profiles=self.profiles, notes=self.notes, t0=round(self.t0, 3))
        (self.raw / "meta.json").write_text(json.dumps(meta, indent=1))
        if et is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location("trace_convert", Path(__file__).with_name("convert.py"))
            conv = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(conv)
            lines = conv.convert(self.raw)
            out = OUT_DIR / f"{self.name}.jsonl"
            conv.write_trace(lines, out)
            kinds = {}
            for l in lines[1:]:
                kinds[l["kind"]] = kinds.get(l["kind"], 0) + 1
            print(f"TRACE {out} {len(lines)} lines {json.dumps(kinds, sort_keys=True)}", flush=True)
        for h in self.homes.values():
            if os.environ.get("CF_KEEP_HOMES"):
                print("kept home", h, flush=True)
            else:
                shutil.rmtree(h, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.workspace, ignore_errors=True)
        return False
