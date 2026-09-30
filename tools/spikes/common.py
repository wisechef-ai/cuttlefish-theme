"""Shared helpers for P0-BIND spikes: temp HERMES_HOME + pexpect/pyte TUI driver."""
import os, sys, json, time, tempfile, shutil, re
import pexpect, pyte

HERMES = os.path.expanduser("~/.local/bin/hermes")
QWEN = "http://100.106.27.136:8000/v1"

def make_home(extra_cfg="", compression=None):
    home = tempfile.mkdtemp(prefix="cf2909-home-")
    cfg = f"""model:
  default: qwen3.8-27b-heretic
  provider: qwen38-local
providers:
  qwen38-local:
    api: {QWEN}
    api_mode: chat_completions
    key_env: QWEN38_API_KEY
    context_length: 1048576
    models:
      qwen3.8-27b-heretic:
        context_length: 1048576
display:
  interface: tui
{extra_cfg}
"""
    open(f"{home}/config.yaml", "w").write(cfg)
    return home

def env_for(home, **kw):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith("HERMES_") and k not in ("HERMES_HOME",):
            e.pop(k)
    e.update(HOME="/home/adam", HERMES_HOME=home, QWEN38_API_KEY="x",
             TERM="xterm-256color", COLORTERM="truecolor", LINES="40", COLUMNS="140")
    e.update(kw)
    return e

class Tui:
    def __init__(self, home, name, args=("--tui",), rows=40, cols=140, **envkw):
        self.name = name
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.raw = b""
        self.p = pexpect.spawn(HERMES, list(args), env=env_for(home, **envkw),
                               dimensions=(rows, cols), timeout=5)
    def pump(self, secs=1.0):
        end = time.time() + secs
        while time.time() < end:
            try:
                d = self.p.read_nonblocking(65536, timeout=0.2)
                self.raw += d; self.stream.feed(d)
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                return False
        return True
    def text(self):
        return "\n".join(l.rstrip() for l in self.screen.display).rstrip()
    def wait_for(self, pat, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            if not self.pump(0.5): return False
            if re.search(pat, self.text()): return True
        return False
    def send(self, s):
        self.p.send(s)
    def line(self, s):
        self.p.send(s); time.sleep(0.3); self.p.send("\r")

def enable_plugin(home, name, src_dir):
    """Copy plugin dir into home/plugins and enable it in config.yaml."""
    dst = f"{home}/plugins/{name}"
    os.makedirs(f"{home}/plugins", exist_ok=True)
    shutil.copytree(src_dir, dst, dirs_exist_ok=True)
    with open(f"{home}/config.yaml", "a") as f:
        f.write(f"plugins:\n  enabled:\n    - {name}\n")

def boot(t, timeout=240):
    """Wait until the TUI status bar says ready (cold home boot takes ~2 min)."""
    end = time.time() + timeout
    while time.time() < end:
        t.pump(2)
        if re.search(r"─ ready", t.text()) or "starting agent" in t.text() and False:
            return True
    return False

def wait_idle(t, timeout=180):
    """Wait for the status bar to show ready (turn finished)."""
    time.sleep(2)
    end = time.time() + timeout
    while time.time() < end:
        t.pump(1.5)
        if re.search(r"─ ready", t.text()) and not re.search(r"running|thinking|waiting", t.text().splitlines()[-2] if len(t.text().splitlines())>1 else ""):
            return True
    return False

def jl(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []
