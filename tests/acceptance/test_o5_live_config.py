"""ACCEPTANCE CONTRACT — O5 (Python half): settings are validated with the SAME vectors as the desktop and served
live by dashboard/plugin_api.py, re-read on every request (no restart) (locked).
"""
from __future__ import annotations

import importlib
import json
import math

import pytest
import yaml

from .helpers import ROOT, load_file_module, plugin_package

VEC = json.loads((ROOT / "contract" / "config-vectors.json").read_text())


def settings_mod():
    plugin_package()
    return importlib.import_module("cuttlefish_theme.cuttlefish.settings")


def _subset(actual, expected, path):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a mapping, got {actual!r}"
        for k, v in expected.items():
            _subset(actual.get(k), v, f"{path}.{k}")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def _dig(o, dotted):
    for k in dotted.split("."):
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


@pytest.mark.parametrize("case", VEC["cases"], ids=[c["name"] for c in VEC["cases"]])
def test_O5_1_python_validator_matches_the_shared_vectors(case):
    settings, warnings = settings_mod().resolve_settings(case["input"])
    _subset(settings, case["expect"], "settings")
    if case.get("exact_defaults"):
        assert settings == VEC["defaults"]
    for a in case.get("absent", []):
        assert _dig(settings, a) is None, f"{a} should have been dropped"
    got = sorted([w["path"], w["code"]] for w in warnings)
    assert got == sorted(case["warnings"])
    assert all(isinstance(w.get("message"), str) and w["message"] for w in warnings)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 1e308 * 10])
def test_O5_2_non_finite_numbers_rejected(bad):
    s, w = settings_mod().resolve_settings({"intensity": bad, "patterns": {"p": {"base": "zebra", "scale": bad}}})
    assert s["intensity"] == 1 and s["patterns"]["p"]["scale"] == 1
    assert len(w) == 2


def test_O5_3_resolve_never_mutates_its_input():
    raw = {"states": {"working": {"pattern": "zebra"}}, "intensity": 7}
    before = json.dumps(raw, sort_keys=True)
    settings_mod().resolve_settings(raw)
    assert json.dumps(raw, sort_keys=True) == before


def _api(tmp_path, monkeypatch, settings):
    home = tmp_path / "hermes-home"
    home.mkdir(exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"entries": {"cuttlefish-theme": {"settings": settings}}}}))
    monkeypatch.setenv("HERMES_HOME", str(home))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = load_file_module("cf_plugin_api_under_test", ROOT / "dashboard" / "plugin_api.py")
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/cuttlefish-theme")
    return home, TestClient(app)


def test_O5_4_plugin_api_serves_settings_and_rereads_them_live(tmp_path, monkeypatch):
    home, client = _api(tmp_path, monkeypatch, {"motion": "alive"})
    r1 = client.get("/api/plugins/cuttlefish-theme/config").json()
    assert r1["settings"]["motion"] == "alive" and r1["warnings"] == []
    (home / "config.yaml").write_text(yaml.safe_dump(
        {"plugins": {"entries": {"cuttlefish-theme": {"settings": {"motion": "wild", "states": {"needs_you": {"pattern": "mottle"}}}}}}}))
    r2 = client.get("/api/plugins/cuttlefish-theme/config").json()
    assert r2["settings"]["motion"] == "still" and r2["settings"]["states"]["needs_you"]["pattern"] == "mottle"
    assert [w["path"] for w in r2["warnings"]] == ["motion"]
    assert r1["rev"] != r2["rev"], "rev changes when the effective settings change"


def test_O5_5_plugin_api_health_and_missing_config(tmp_path, monkeypatch):
    home, client = _api(tmp_path, monkeypatch, {})
    (home / "config.yaml").unlink()
    r = client.get("/api/plugins/cuttlefish-theme/config")
    assert r.status_code == 200 and r.json()["settings"] == VEC["defaults"]
    (home / "config.yaml").write_text(":: not yaml ::\n  - [")
    r = client.get("/api/plugins/cuttlefish-theme/config")
    assert r.status_code == 200 and r.json()["settings"] == VEC["defaults"] and r.json()["warnings"], "broken YAML degrades"
    h = client.get("/api/plugins/cuttlefish-theme/health").json()
    assert h["ok"] is True and h["version"] == yaml.safe_load((ROOT / "plugin.yaml").read_text())["version"]


def test_O5_6_dashboard_manifest_mounts_the_api():
    m = json.loads((ROOT / "dashboard" / "manifest.json").read_text())
    assert m["name"] == "cuttlefish-theme" and m["api"] == "plugin_api.py"
