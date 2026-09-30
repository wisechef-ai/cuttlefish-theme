"""Unit tests for the desktop spike fixtures + runner (no Electron, no display).

These pin the parts of the P0-DESK harness that a spike re-run silently depends on:
the scratch unified package's shape, its backend route contract (spike 08 reads
`marker`/`hermes_home` to prove local-vs-remote routing), and the runner's refusal
to touch a live display.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
SPIKES = TOOLS / "spikes"
FIXTURE = SPIKES / "fixtures" / "cf-spike"
RUNNER = SPIKES / "run-desktop.sh"


def _load_plugin_api():
    spec = importlib.util.spec_from_file_location(
        "cf_spike_plugin_api", FIXTURE / "dashboard" / "plugin_api.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fixture_is_a_unified_package():
    manifest = yaml.safe_load((FIXTURE / "plugin.yaml").read_text())
    assert manifest["name"] == FIXTURE.name == "cf-spike"
    for rel in ("__init__.py", "desktop/plugin.js", "dashboard/manifest.json", "dashboard/plugin_api.py"):
        assert (FIXTURE / rel).is_file(), rel


def test_dashboard_manifest_names_the_api_module():
    dash = json.loads((FIXTURE / "dashboard" / "manifest.json").read_text())
    assert dash["name"] == "cf-spike"
    assert (FIXTURE / "dashboard" / dash["api"]).is_file()


def test_ping_reports_which_backend_served_it(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HERMES_HOME", "/tmp/cf-test-home")
    monkeypatch.setenv("CF_SPIKE_BACKEND_MARKER", "remote")
    app = fastapi.FastAPI()
    app.include_router(_load_plugin_api().router, prefix="/api/plugins/cf-spike")
    client = TestClient(app)

    body = client.get("/api/plugins/cf-spike/ping").json()
    assert body["plugin"] == "cf-spike"
    assert body["marker"] == "remote"
    assert body["hermes_home"] == "/tmp/cf-test-home"
    assert isinstance(body["pid"], int)

    with client.websocket_connect("/api/plugins/cf-spike/events") as ws:
        assert ws.receive_json()["tick"] == 1


def test_agent_half_is_inert():
    spec = importlib.util.spec_from_file_location("cf_spike_init", FIXTURE / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.register(object()) is None


@pytest.mark.parametrize("display", [":0", ":1"])
def test_runner_refuses_live_displays_before_doing_anything(display, tmp_path):
    proc = subprocess.run(
        ["bash", str(RUNNER), "14-playwright-real-electron"],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CF_DISPLAY": display},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2
    assert "refusing" in proc.stderr


def test_runner_parses():
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)


def test_every_spike_dir_has_a_run_entrypoint():
    dirs = [d for d in SPIKES.iterdir() if d.is_dir() and d.name[:2].isdigit()]
    desktop = {"07", "08", "09", "10", "14"}
    assert {d.name[:2] for d in dirs} >= desktop
    for d in dirs:
        if d.name[:2] in desktop:
            # run-desktop.sh invokes <spike>/run.ts, so desktop spikes need exactly that.
            assert (d / "run.ts").is_file(), d.name
        else:
            # Terminal/TUI/binding spikes run outside Electron via their own
            # run-*.sh (12, 15) or run*.py (01-06, 11, 13) entrypoint.
            assert (
                (d / "run.ts").is_file() or any(d.glob("run*.sh")) or any(d.glob("run*.py"))
            ), d.name


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_fixture_plugin_js_parses_as_esm():
    # tools/package.json is "type": "module", so --check parses it as ESM without
    # resolving @hermes/plugin-sdk (which only exists inside the desktop app).
    subprocess.run(["node", "--check", str(FIXTURE / "desktop" / "plugin.js")], check=True)
