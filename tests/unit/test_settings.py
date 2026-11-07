"""Unit: cuttlefish.settings — edges the shared vectors leave open."""

from __future__ import annotations

import json
import math

import pytest
from cuttlefish_theme.cuttlefish import settings as S


def codes(warnings):
    return sorted((w["path"], w["code"]) for w in warnings)


def test_defaults_are_the_contract_defaults():
    vec = json.loads(open("contract/config-vectors.json").read())
    assert S.DEFAULT_SETTINGS == vec["defaults"]
    settings, warnings = S.resolve_settings({})
    assert settings == vec["defaults"] and warnings == []


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 1e308 * 10])
def test_non_finites_are_range_rejections(bad):
    settings, warnings = S.resolve_settings({"intensity": bad, "patterns": {"p": {"base": "zebra", "scale": bad}}})
    assert settings["intensity"] == 1 and settings["patterns"]["p"]["scale"] == 1
    assert codes(warnings) == [("intensity", "range"), ("patterns.p.scale", "range")]


def test_repeated_resolves_never_alias_the_defaults():
    first, _ = S.resolve_settings({"states": {"working": {"label": "x"}}})
    first["states"]["working"]["label"] = "mutated"
    second, _ = S.resolve_settings({})
    assert second["states"]["working"]["label"] == "working"


def test_input_is_never_mutated_nested():
    raw = {"states": {"working": {"pattern": "zebra"}}, "patterns": {"mottle": {"contrast": 1.3}}}
    before = json.dumps(raw, sort_keys=True)
    S.resolve_settings(raw)
    assert json.dumps(raw, sort_keys=True) == before


def test_label_boundary_is_24():
    ok, warnings = S.resolve_settings({"states": {"working": {"label": "x" * 24}}})
    assert ok["states"]["working"]["label"] == "x" * 24 and warnings == []
    bad, warnings = S.resolve_settings({"states": {"working": {"label": "x" * 25}}})
    assert bad["states"]["working"]["label"] == "working"
    assert codes(warnings) == [("states.working.label", "range")]


def test_priority_boundaries():
    ok, warnings = S.resolve_settings({"states": {"working": {"priority": -1000}}})
    assert ok["states"]["working"]["priority"] == -1000 and warnings == []
    ok, warnings = S.resolve_settings({"states": {"working": {"priority": 1000}}})
    assert ok["states"]["working"]["priority"] == 1000 and warnings == []
    _, warnings = S.resolve_settings({"states": {"working": {"priority": 1001}}})
    assert codes(warnings) == [("states.working.priority", "range")]


def test_unhashable_and_odd_types_never_raise():
    for raw in (
        {"states": {"x": {"when": ["busy"], "pattern": ["zebra"], "priority": 5}}},
        {"states": {"x": {"when": "busy", "pattern": {"a": 1}, "priority": 5}}},
        {"states": {"working": {"when": 5, "priority": "x", "label": 9}}},
        {"patterns": {"p": {"base": ["mottle"]}}},
        {"patterns": {"p": {"base": "mottle", "density": [1]}}},
        {"states": 3, "patterns": 7, "intensity": "x", "motion": [], "extra": {"k": 1}},
        [1, {"a": 2}],
    ):
        settings, warnings = S.resolve_settings(raw)
        assert settings["motion"] == "still" or raw.get("motion") != []
        assert all(w["message"] for w in warnings)


def test_null_entries():
    settings, warnings = S.resolve_settings({"states": {"finished_unseen": None, "ghost": None},
                                             "patterns": {"eyespot": None, "phantom": None}})
    assert "finished_unseen" not in settings["states"] and "resting" in settings["states"]
    assert "eyespot" in settings["patterns"]
    assert codes(warnings) == [("patterns.eyespot", "required")]


def test_new_state_rejections_drop_whole():
    _, warnings = S.resolve_settings({"states": {"x": {"when": "busy", "pattern": "zebra", "priority": 9999}}})
    assert codes(warnings) == [("states.x.priority", "range")]


def test_user_pattern_cycles_do_not_leak():
    settings, warnings = S.resolve_settings({"patterns": {"a": {"base": "mottle"}}, "states": {"working": {"pattern": "a"}}})
    assert settings["states"]["working"]["pattern"] == "a" and settings["patterns"]["a"]["scale"] == 1
    assert warnings == []


@pytest.mark.parametrize("bad_when", ["zzz", 5, ["busy"], {"when": "busy"}])
def test_preset_rejected_when_keeps_its_default(bad_when):
    settings, warnings = S.resolve_settings({"states": {"working": {"when": bad_when}}})
    assert settings["states"]["working"]["when"] == "busy"
    assert codes(warnings) == [("states.working.when", "enum")]


def test_new_pattern_with_only_a_base_gets_unit_parameters():
    settings, warnings = S.resolve_settings({"patterns": {"mine": {"base": "zebra"}}})
    assert settings["patterns"]["mine"] == {"base": "zebra", "density": 1, "contrast": 1, "scale": 1}
    assert warnings == []
