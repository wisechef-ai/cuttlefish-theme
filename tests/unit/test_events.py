"""Unit: cuttlefish.events — the one door out."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def events():
    from cuttlefish_theme import cuttlefish  # noqa: F401 - bind the package first
    return importlib.import_module("cuttlefish_theme.cuttlefish.events")


def test_prefix_names_the_plugin(events):
    assert events.EVENT_PREFIX == "plugin.cuttlefish-theme."
    assert events.PLUGIN_ID == "cuttlefish-theme"


def test_emit_goes_through_the_seam(events):
    got: list[tuple] = []
    events.set_broadcaster(lambda plugin_id, event, payload=None: got.append((plugin_id, event, payload)))
    try:
        events.emit("needs_you", {"session_id": "S"})
    finally:
        events.set_broadcaster(None)
    assert got == [("cuttlefish-theme", "needs_you", {"session_id": "S"})]


def test_emit_with_the_default_door_and_no_hermes_is_a_silent_noop(events):
    """No Hermes on this venv's path: the lazy core import must not escape."""
    events.set_broadcaster(None)
    events.emit("needs_you", {"session_id": "S"})  # no raise, no import error


def test_emit_swallows_a_broken_seam(events):
    def boom(*a, **k):
        raise RuntimeError("gateway gone")

    events.set_broadcaster(boom)
    try:
        events.emit("error", {"session_id": "S"})
    finally:
        events.set_broadcaster(None)


def test_the_default_door_is_the_public_core_one(events):
    src = open(events.__file__).read()
    assert "hermes_cli.plugin_events" in src and "broadcast_plugin_event" in src
