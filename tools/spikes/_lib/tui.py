"""Shared pty harness: drive the real `hermes --tui` against a throwaway HERMES_HOME."""
import os, pty, select, signal, struct, fcntl, termios, time, tempfile, shutil, subprocess
import pyte

HOME = os.environ.get("HOME", "/home/adam")
HERMES_SRC = os.environ.get("CF_HERMES_SRC", f"{HOME}/.hermes/hermes-agent")


def make_home():
    h = tempfile.mkdtemp(prefix="cf-spike-home-")
    os.makedirs(f"{h}/tui-widgets", exist_ok=True)
    # offline: point at a dead local endpoint, never a real provider
    with open(f"{h}/config.yaml", "w") as f:
        f.write("model:\n  default: stub\n  provider: custom\n  base_url: http://127.0.0.1:9/v1\n  api_key: stub\n"
                "display:\n  interface: tui\n")
    return h


class Tui:
    def __init__(self, home, cols=120, rows=40, env_extra=None, cmd=None):
        self.home, self.cols, self.rows = home, cols, rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.raw = bytearray()
        # clean env: parent agent sessions leak HERMES_* (QUIET, SINGLE_QUERY...) that change TUI behaviour
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERMES_", "_HERMES", "TERMINAL_", "COGNEE", "AI_AGENT", "NO_COLOR"))}
        env.update(HOME=HOME, HERMES_HOME=home, TERM="xterm-256color", COLORTERM="truecolor")
        if cmd is None and os.environ.get("CF_VIA_LAUNCHER") != "1":
            # Bypass the python launcher's update/build preflight (it rebuilds the desktop app on a fresh
            # HERMES_HOME and contends with other lanes) and exec what it execs: node --expose-gc dist/entry.js
            # with the env _launch_tui() sets. Same TUI bundle, same tui_gateway child.
            env.update(HERMES_PYTHON=f"{HERMES_SRC}/venv/bin/python3", HERMES_PYTHON_SRC_ROOT=HERMES_SRC,
                       HERMES_CWD=HOME, NODE_ENV="production", HERMES_TUI_NATIVE="0",
                       HERMES_TUI_ACTIVE_SESSION_FILE=f"{home}/active-session.json",
                       NODE_OPTIONS="--max-old-space-size=4096")
            cmd = [os.environ.get("CF_NODE", shutil.which("node") or "node"), "--expose-gc",
                   f"{os.environ.get('CF_TUI_DIST', HERMES_SRC + '/ui-tui')}/dist/entry.js"]
        env.update(env_extra or {})
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(cmd[0] if cmd else "hermes", cmd or ["hermes", "--tui"], env)
        self.resize(cols, rows, first=True)

    def resize(self, cols, rows, first=False):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.cols, self.rows = cols, rows
        self.screen.resize(rows, cols)
        if not first:
            os.kill(self.pid, signal.SIGWINCH)

    def pump(self, secs=1.0):
        end = time.time() + secs
        n = 0
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    d = os.read(self.fd, 65536)
                except OSError:
                    break
                if not d:
                    break
                n += len(d)
                self.raw += d
                self.stream.feed(d)
        return n

    def send(self, b):
        os.write(self.fd, b if isinstance(b, bytes) else b.encode())

    def text(self):
        return "\n".join(self.screen.display)

    def wait_for(self, needle, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.3)
            if needle in self.text():
                return True
        return False

    def child_pids(self):
        out = subprocess.run(["pgrep", "-P", str(self.pid)], capture_output=True, text=True).stdout.split()
        return [int(x) for x in out]

    def close(self):
        try:
            os.kill(self.pid, signal.SIGTERM)
            time.sleep(0.3)
            os.kill(self.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except OSError:
            pass
