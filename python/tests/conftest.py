"""Shared fixtures: every test runs against a throwaway HERMES_HOME, never ~/.hermes."""
import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "hermes-home"
    h.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(h))
    return h


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


@pytest.fixture
def clock():
    return Clock()


def _make_state_db(home, rows):
    """rows: [(id, parent_session_id, title)] -> <home>/state.db with a sessions table."""
    import sqlite3
    con = sqlite3.connect(str(home / "state.db"))
    con.execute("create table sessions (id text primary key, parent_session_id text, title text)")
    con.executemany("insert into sessions values (?,?,?)", rows)
    con.commit()
    con.close()


@pytest.fixture
def make_state_db():
    return _make_state_db


# ---- TS bundle bridge (cross-language parity) ----------------------------------------------------
import json as _json
import pathlib as _pathlib
import shutil as _shutil
import subprocess as _subprocess

REPO = _pathlib.Path(__file__).resolve().parents[2]
TUI_BUNDLE = REPO / "tui" / "core.bundle.mjs"
TRACES = REPO / "tools" / "traces"


@pytest.fixture(scope="session")
def ts():
    """``ts(js_body, payload)``: run ``js_body`` in node against tui/core.bundle.mjs.

    The body sees ``core`` (the bundle's exports) and ``input`` (payload) and must ``return`` a
    JSON-serialisable value. Fails (never skips) when node is missing: parity must not go silent."""
    node = _shutil.which("node")
    assert node, "node is required for the cross-language parity tests"
    assert TUI_BUNDLE.exists(), TUI_BUNDLE

    def run(body, payload):
        prog = ("import {readFileSync} from 'node:fs';"
                f"const core = await import({_json.dumps(TUI_BUNDLE.as_uri())});"
                "const input = JSON.parse(readFileSync(0, 'utf8'));"
                f"const out = await (async () => {{ {body} }})();"
                "process.stdout.write(JSON.stringify(out));")
        r = _subprocess.run([node, "--input-type=module", "-e", prog], input=_json.dumps(payload),
                            capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr
        return _json.loads(r.stdout)

    return run


# ---- CLI fixtures -------------------------------------------------------------------------------
class FakeCore:
    """Stands in for hermes_api.Core: the config is a dict persisted nowhere; a file at config_path marks it 'existing'."""

    def __init__(self, home, config=None):
        self.home = home
        self.config = config
        self.writes = []
        self.removed = 0

    @property
    def config_path(self):
        return self.home / "config.yaml"

    def read_config(self):
        import copy
        return copy.deepcopy(self.config or {})

    def write_config(self, data):
        import copy
        self.config = copy.deepcopy(data)
        self.writes.append(copy.deepcopy(data))
        self.config_path.write_text("fake\n")

    def remove_plugin(self):
        self.removed += 1
        return 0, "ok"


@pytest.fixture
def fakecore(home):
    return FakeCore(home, {})


@pytest.fixture
def pkg(tmp_path):
    """A package root shipping every artifact; tests delete files to model 'not in this build'."""
    root = tmp_path / "pkg"
    for rel, body in (("skins/cuttlefish.yaml", "name: cuttlefish\ncolors:\n  ui_accent: \"#00a1cb\"\n"),
                      ("tui/cuttlefish.mjs", "export default {}\n"),
                      ("desktop/plugin.js", "export default {}\n"),
                      ("cli/cuttlefish_widget.py", "def create(api):\n    return None\n")):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


def tree(root):
    """{relative path: ('d',) | ('l', target) | ('f', bytes)} for every entry under root."""
    import os
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in dn + fn:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out[rel] = ("l", os.readlink(p))
            elif os.path.isdir(p):
                out[rel] = ("d",)
            else:
                out[rel] = ("f", open(p, "rb").read())
    return out
