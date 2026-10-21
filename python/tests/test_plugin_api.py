"""dashboard/plugin_api.py: GET /identity and GET /state per CONTRACT §6. Read-only."""
import importlib.util
import json
import pathlib
import sys

import pytest

from cuttlefish_theme.python import hooks as H
from cuttlefish_theme.python import paths as P

API = pathlib.Path(__file__).resolve().parents[2] / "dashboard" / "plugin_api.py"


@pytest.fixture
def api(home, clock, monkeypatch):
    # loaded the way core loads it: standalone, by file path, no package context
    name = "hermes_dashboard_plugin_cuttlefish_test"
    spec = importlib.util.spec_from_file_location(name, API)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_now", clock)
    monkeypatch.setattr(mod, "_host", lambda: "box")
    monkeypatch.setattr(mod, "_pid_alive", lambda pid: True)
    yield mod
    sys.modules.pop(name, None)


def runtime(home, clock):
    return H.Runtime(home, clock=clock, pid=4242, host="box", pid_alive=lambda p: True, heartbeat_interval=60)


def snapshot(home):
    return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in home.rglob("*") if p.is_file()}


def test_identity_empty_home(api, home):
    out = api.identity()
    assert out["schema"] == "cf2909.identity/1" and out["sessions"] == {} and out["host"] == "box"


def test_identity_returns_the_file_plus_host(api, home, clock):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    out = api.identity()
    on_disk = json.loads(P.identity_file(home).read_text())
    assert out["host"] == "box" and out["sessions"] == on_disk["sessions"] and out["rev"] == on_disk["rev"]


def test_state_resolves_and_shapes_each_session(api, home, clock):
    cb = runtime(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s1")
    clock.advance(10)
    cb["pre_tool_call"](session_id="s1", tool_name="clarify", tool_call_id="c1")
    clock.advance(7)
    out = api.state()
    assert out["schema"] == "cf2909.state-api/1" and out["now"] == clock() and isinstance(out["rev"], int)
    s = out["sessions"]["s1"]
    assert s["state"] == "needs-you" and s["raw_state"] == "needs-you"
    assert s["since"] == clock() - 7 and s["durable_id"] == "s1"
    assert s["hue_deg"] == json.loads(P.identity_file(home).read_text())["sessions"]["s1"]["hue_deg"]
    assert s["name"].startswith("s-") and s["alarm_age_s"] == 7


def test_state_non_alarm_has_null_alarm_age(api, home, clock):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    assert api.state()["sessions"]["s1"]["alarm_age_s"] is None


def test_stale_heartbeat_resolves_to_unknown_but_keeps_raw_state(api, home, clock):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    clock.advance(31)
    s = api.state()["sessions"]["s1"]
    assert s["state"] == "unknown" and s["raw_state"] == "thinking"


def test_dead_owner_pid_on_this_host_is_unknown(api, home, clock, monkeypatch):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    monkeypatch.setattr(api, "_pid_alive", lambda pid: False)
    assert api.state()["sessions"]["s1"]["state"] == "unknown"


def test_remote_owner_is_not_pid_probed(api, home, clock, monkeypatch):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    monkeypatch.setattr(api, "_host", lambda: "elsewhere")
    monkeypatch.setattr(api, "_pid_alive", lambda pid: pytest.fail("must not probe a remote pid"))
    assert api.state()["sessions"]["s1"]["state"] == "thinking"


def test_rev_is_stable_when_nothing_changed_and_moves_when_it_does(api, home, clock):
    cb = runtime(home, clock).callbacks()
    cb["pre_llm_call"](session_id="s1")
    r1 = api.state()["rev"]
    clock.advance(5)  # time passes, heartbeat refreshes, nothing else
    assert api.state()["rev"] == r1
    cb["on_session_end"](session_id="s1", completed=True)
    assert api.state()["rev"] != r1


def test_missing_and_corrupt_files_are_tolerated(api, home, clock):
    assert api.state()["sessions"] == {}
    (P.bus_dir(home)).mkdir(parents=True)
    (P.bus_dir(home) / "bad.json").write_text("{x")
    assert api.state()["sessions"] == {}


def test_handlers_never_write(api, home, clock):
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    before = snapshot(home)
    api.identity()
    api.state()
    assert snapshot(home) == before


def test_over_http_with_the_fastapi_test_client(api, home, clock):
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    app = fastapi.FastAPI()
    app.include_router(api.router, prefix="/api/plugins/cuttlefish-theme")
    runtime(home, clock).callbacks()["pre_llm_call"](session_id="s1")
    c = testclient.TestClient(app)
    ident = c.get("/api/plugins/cuttlefish-theme/identity")
    st = c.get("/api/plugins/cuttlefish-theme/state")
    assert ident.status_code == 200 and "s1" in ident.json()["sessions"]
    assert st.status_code == 200 and st.json()["sessions"]["s1"]["state"] == "thinking"
