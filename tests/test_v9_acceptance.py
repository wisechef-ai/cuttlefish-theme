"""The mantle CLASSES must survive terminal quantisation.

Named for v9, when this file also held the transcript-mantle acceptance tests.
Those are gone (see the note below); what remains is the guarantee that the
per-session pigment classes still read as COLOUR rather than grey once the
terminal has quantised them — a contract the input rule and status bar depend
on, since both draw from the same classes.
"""
from __future__ import annotations

import pytest


# The five v9 transcript-mantle acceptance tests that lived here are DELETED,
# not weakened. They pinned "the transcript line paints a filled per-cell
# background" (filled fragments, row-to-row variation, ~30% pigment, AA against
# the body foreground) — a contract Adam overturned on 2026-09-13 in favour of a
# flat, unpainted transcript. Their replacement is tests/test_flat_transcript.py,
# which asserts the opposite and was proven RED against this behaviour.
#
# Kept below: the quantisation contract, which is about the mantle CLASSES.
# Those still ship — the input rule and the status bar draw from them — so the
# "must not collapse onto the greyscale ramp" guarantee is still load-bearing.

@pytest.mark.parametrize("session_id", [
    "zivyra", "koralen", "tori-main", "chef", "wise", "mantis", "tilola", "sepia"])
def test_mantle_pigment_survives_terminal_quantisation(session_id):
    """The mantle must still read as COLOUR on the terminal, not grey.

    prompt_toolkit renders at DEPTH_8_BIT: our truecolor `48;2;r;g;b` is
    quantised to an xterm-256 index before it reaches the screen. The 256-cube
    is sparse in the dark region, so a low-chroma near-black pigment collapses
    onto the GREYSCALE ramp (232-255) and the mantle reads as flat grey — which
    is exactly what a user reported while every byte-level test passed.

    Assert on the QUANTISED index, the way the terminal actually sees it.
    """
    from cuttlefish_theme.chrome import _mantle_classes, _mantle_palette
    from cuttlefish_theme.color.terminal import quantize_256

    ground_index = quantize_256(_mantle_palette(session_id))
    pigments = [p for p in _mantle_classes(session_id, "resting")
                if quantize_256(p) != ground_index]
    # The ground is the band's darkest step, so it IS one of the classes now;
    # what matters is that pigment remains above it, and that none of it is grey.
    assert pigments, "every class collapsed onto the ground"
    for pigment in pigments:
        pigment_index = quantize_256(pigment)
        # 232-255 is the greyscale ramp: landing there means the hue is gone.
        assert not 232 <= pigment_index <= 255, (
            f"pigment quantised to grey index {pigment_index} — the mantle has no colour")
