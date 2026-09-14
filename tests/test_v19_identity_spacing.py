"""Concurrent sessions must not look alike.

WHY THIS CONTRACT EXISTS

The README promises, in the section a new user reads first:

    "allocation maximises perceptual distance, so concurrent sessions never
     look alike"

Measured on v19 before this contract existed, that was false about 8% of the
time. Twelve randomly-generated six-window desktops gave worst-pair OKLab
separations of:

    0.004 0.023 0.024 0.037 0.048 0.050 0.052 0.055 0.059 0.061 0.083 0.086

A just-noticeable difference is roughly 0.02, so 1 of those 12 desktops held a
pair a human cannot tell apart, and three more sat on the edge. The background
is the channel the user navigates by; two windows sharing a face is the one
failure that breaks its whole job.

THE CAUSE, ALREADY DIAGNOSED

Every piece needed already existed and they were simply not connected:

  * color/identity.py  ``allocate(session_id, live=...)`` does real
    farthest-point selection against the colours of other visible sessions.
  * session.py         ``read_registry()`` reads Hermes' live-session registry
    at ``<HERMES_HOME>/runtime/active_sessions.json`` (7 real entries when this
    was written).
  * chrome.py:108      called ``allocate(session_id)`` with ``live`` defaulting
    to EMPTY, so it always took the "alone" path.

So the allocator was never told what it was meant to avoid.

WHAT THIS CONTRACT DOES NOT REQUIRE

It does not require a specific colour for a specific session, and it does not
require the registry to be present. A session that is alone, or that cannot read
the registry, must still get a stable colour — degrading to the current
behaviour is correct, crashing or going grey is not.
"""

from __future__ import annotations

import math
from itertools import combinations

import pytest

identity = pytest.importorskip("cuttlefish_theme.v19.identity")

# A just-noticeable difference in OKLab is ~0.02. The floor is set at 0.04 so a
# pair must be comfortably apart, not merely technically distinct: measured, an
# unspaced allocator produced 0.0035 at worst.
MIN_SEPARATION = 0.04

# Six windows is the case the README's own "Why" section describes.
DESKTOP_SIZE = 6


def _separation(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    """Euclidean OKLab distance between two identity centroids."""
    return math.dist(left, right)


class TestSpacingAgainstLiveSessions:
    """Outcome 1-4: the allocator is told what it must avoid."""

    def test_identity_for_accepts_a_live_set(self):
        """The function exists and takes the neighbours it must avoid."""
        colour = identity.identity_for("solo", live=())
        assert len(colour) == 3

    def test_six_concurrent_sessions_are_all_distinguishable(self):
        """The README's promise, measured."""
        ids = [f"desk-{n}" for n in range(DESKTOP_SIZE)]
        placed: list[tuple[float, float, float]] = []
        for session_id in ids:
            placed.append(identity.identity_for(session_id, live=tuple(placed)))
        worst = min(_separation(a, b) for a, b in combinations(placed, 2))
        assert worst >= MIN_SEPARATION, f"closest pair only {worst:.4f} apart"

    def test_crowding_degrades_gracefully_not_catastrophically(self):
        """Twelve sessions still may not produce an invisible pair."""
        placed: list[tuple[float, float, float]] = []
        for n in range(12):
            placed.append(identity.identity_for(f"crowd-{n}", live=tuple(placed)))
        worst = min(_separation(a, b) for a, b in combinations(placed, 2))
        assert worst >= 0.02, f"closest pair only {worst:.4f} apart — below JND"

    def test_a_session_alone_still_gets_a_colour(self):
        """No registry, no neighbours, still a usable identity."""
        colour = identity.identity_for("alone", live=())
        assert len(colour) == 3
        assert any(channel > 0 for channel in colour)


class TestStabilityIsPreserved:
    """Outcome 5-7: spacing must not cost determinism."""

    def test_the_same_inputs_give_the_same_colour(self):
        first = identity.identity_for("stable", live=(("x", 0.5, 0.1),))
        second = identity.identity_for("stable", live=(("x", 0.5, 0.1),))
        assert first == second

    def test_different_sessions_differ_even_with_no_neighbours(self):
        """The hash path must still separate sessions when live is empty."""
        colours = {identity.identity_for(f"s-{n}", live=()) for n in range(8)}
        assert len(colours) >= 7, "the unspaced path must not collapse sessions"

    def test_a_reconnecting_session_keeps_its_colour(self):
        """Same id, same neighbours, same face — that is what reconnect means."""
        neighbours = (("a", 0.4, 0.05), ("b", 0.6, -0.05))
        before = identity.identity_for("returning", live=neighbours)
        after = identity.identity_for("returning", live=neighbours)
        assert before == after


class TestTheRegistryIsRead:
    """Outcome 8-9: the live set comes from somewhere real."""

    def test_live_identities_returns_a_tuple(self):
        """Whatever the registry holds, the result must be usable as `live`."""
        assert isinstance(identity.live_identities(), tuple)

    def test_a_missing_registry_is_not_an_error(self, tmp_path):
        """A theme may not crash a terminal because a JSON file is absent."""
        assert isinstance(identity.live_identities(tmp_path / "nope.json"), tuple)
