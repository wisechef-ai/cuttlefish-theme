"""Rendering must not mutate the snapshot used to allocate other sessions."""
from __future__ import annotations

import pytest

from cuttlefish_theme.v19 import renderer


def test_rendering_does_not_change_registry_snapshot(monkeypatch):
    registry = {"registered": (0.55, 0.08, 0.12)}
    original = dict(registry)
    renderer.clear_caches()
    monkeypatch.setattr(renderer, "_registry_identities", lambda: registry)
    monkeypatch.setattr(renderer.identity, "identity_for", lambda *args, **kwargs: (0.6, 0.1, 0.05))
    try:
        renderer.transcript_row("new-session", 20, 0, 0, False)
        renderer.transcript_row("registered", 20, 0, 0, False)
        assert registry == original, "painting modified the shared registry snapshot"
    finally:
        renderer._observed_identities.clear()
