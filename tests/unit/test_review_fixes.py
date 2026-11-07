"""Unit: the review round's BEHAVIOUR fixes (each fails at e07b558 on behaviour).

R1 settings never raise on huge ints; R2 config.yaml of any shape degrades to
defaults + a warning instead of raising; R3 no producer text rides the wire in
the ``kind`` field.
"""

from __future__ import annotations

import importlib
import json

import pytest
from cuttlefish_theme.cuttlefish import liveconfig
from cuttlefish_theme.cuttlefish import settings as S

SECRET = "SECRET-TOKEN-xyz"


@pytest.mark.parametrize("raw", [
    {"intensity": 10**400},
    {"patterns": {"mottle": {"density": -(10**400)}}},
    {"patterns": {"p": {"base": "zebra", "scale": 10**400}}},
    {"states": {"resting": {"priority": 10**400}}},
    {"states": {"x": {"when": "idle", "pattern": "mottle", "priority": 10**400}}},
])
def test_R1_huge_ints_are_a_range_warning_not_a_crash(raw):
    settings, warnings = S.resolve_settings(raw)
    assert settings["intensity"] == 1 and settings["states"]["resting"]["priority"] == 0
    assert any(w["code"] == "range" for w in warnings)


def test_R1_in_range_ints_and_floats_still_pass():
    settings, warnings = S.resolve_settings({"intensity": 2, "patterns": {"mottle": {"density": 0.25}}})
    assert settings["intensity"] == 2 and settings["patterns"]["mottle"]["density"] == 0.25 and warnings == []


@pytest.mark.parametrize("payload", [b"\xff\xfe\x00bad\x80", ("[" * 5000).encode()])
def test_R2_hostile_config_bytes_degrade_with_a_warning(tmp_path, payload):
    (tmp_path / "config.yaml").write_bytes(payload)
    settings, warnings = liveconfig.resolve_live(tmp_path)
    assert settings == S.DEFAULT_SETTINGS
    assert [w["path"] for w in warnings] == ["config"]


@pytest.fixture
def sent():
    from cuttlefish_theme import cuttlefish  # noqa: F401
    events = importlib.import_module("cuttlefish_theme.cuttlefish.events")
    got: list[tuple[str, dict]] = []
    events.set_broadcaster(lambda _pid, event, payload=None: got.append((event, dict(payload or {}))))
    yield got
    events.set_broadcaster(None)


@pytest.mark.parametrize("kind", [SECRET, "rm -rf /", 7, ["a"]])
def test_R3_an_unknown_kind_never_rides_the_wire(sent, kind):
    from cuttlefish_theme import cuttlefish  # noqa: F401
    hooks = importlib.import_module("cuttlefish_theme.cuttlefish.hooks")
    hooks.on_human_input_request(session_id="s", session_key="k", kind=kind, request_id="r1")
    hooks.pre_approval_request(session_id="s", session_key="k2", kind=kind, request_id="r2")
    assert sent and SECRET not in json.dumps(sent) and "rm -rf" not in json.dumps(sent)
    assert {p["kind"] for _, p in sent} <= {"approval", "clarify", "sudo", "other"}


@pytest.mark.parametrize("kind", ["approval", "clarify", "sudo"])
def test_R3_known_kinds_pass_through(sent, kind):
    from cuttlefish_theme import cuttlefish  # noqa: F401
    hooks = importlib.import_module("cuttlefish_theme.cuttlefish.hooks")
    hooks.on_human_input_request(session_id="s", session_key="k", kind=kind, request_id="r")
    assert sent[0][1]["kind"] == kind


def test_R4_entry_warnings_name_their_kind_in_words():
    """The shared null/non-mapping path says 'state' or 'pattern' (kills the [:-1] mutants)."""
    _, w = S.resolve_settings({"states": {"resting": None, "x": 5}, "patterns": {"mottle": None, "y": 5}})
    by_path = {x["path"]: x["message"] for x in w}
    assert "built-in state 'resting'" in by_path["states.resting"]
    assert by_path["states.x"].startswith("state 'x'")
    assert "built-in pattern 'mottle'" in by_path["patterns.mottle"]
    assert by_path["patterns.y"].startswith("pattern 'y'")
