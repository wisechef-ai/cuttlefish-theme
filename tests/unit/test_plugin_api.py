"""Unit: dashboard/plugin_api.py — loaded the way the web server loads it."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

# Not resolve(): under the mutator's symlink overlays a resolved path points at
# the original tree, and the mutated copy under test would never be loaded.
ROOT = Path(__file__).parents[2]


def api(monkeypatch, tmp_path, settings=None, text=None):
    home = tmp_path / "hermes-home"
    home.mkdir(exist_ok=True)
    if text is not None:
        (home / "config.yaml").write_text(text)
    elif settings is not None:
        (home / "config.yaml").write_text(yaml.safe_dump(
            {"plugins": {"entries": {"cuttlefish-theme": {"settings": settings}}}}))
    monkeypatch.setenv("HERMES_HOME", str(home))
    spec = importlib.util.spec_from_file_location("cf_api_unit", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/cuttlefish-theme")
    return home, TestClient(app)


def test_config_rev_is_stable_until_the_answer_changes(tmp_path, monkeypatch):
    _, client = api(monkeypatch, tmp_path, {"motion": "alive"})
    r1 = client.get("/api/plugins/cuttlefish-theme/config").json()
    r2 = client.get("/api/plugins/cuttlefish-theme/config").json()
    assert r1 == r2 and r1["rev"], "same config, same rev"
    (tmp_path / "hermes-home" / "config.yaml").write_text(yaml.safe_dump(
        {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "off"}}}}}))
    r3 = client.get("/api/plugins/cuttlefish-theme/config").json()
    assert r3["settings"]["motion"] == "off" and r3["rev"] != r1["rev"]


def test_health(tmp_path, monkeypatch):
    _, client = api(monkeypatch, tmp_path)
    body = client.get("/api/plugins/cuttlefish-theme/health").json()
    assert body["ok"] is True
    assert body["version"] == str(yaml.safe_load((ROOT / "plugin.yaml").read_text())["version"])


def test_broken_yaml_degrades_to_defaults_plus_warning(tmp_path, monkeypatch):
    _, client = api(monkeypatch, tmp_path, text="]not yaml[")
    body = client.get("/api/plugins/cuttlefish-theme/config").json()
    assert body["settings"]["motion"] == "still" and body["warnings"]


def test_the_router_serves_exactly_the_two_paths(tmp_path, monkeypatch):
    _, client = api(monkeypatch, tmp_path)
    assert client.get("/api/plugins/cuttlefish-theme/config").status_code == 200
    assert client.get("/api/plugins/cuttlefish-theme/health").status_code == 200
    for stray in ("status", "settings", "config/extra"):
        assert client.get(f"/api/plugins/cuttlefish-theme/{stray}").status_code == 404, stray
