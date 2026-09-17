"""`band` exists to guarantee two numbers. These pin both."""
from cuttlefish_theme.band import band, families, family_of
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import contrast_ratio

FOREGROUND = "#E8E6EA"


def test_the_band_is_narrow_enough_to_read_text_across():
    """Legibility is a SPREAD problem, not a per-colour one.

    Every colour here individually cleared contrast before v13 and the result was
    still "hard to be used": a line of text crossed backgrounds varying 3.06x, so
    the eye adapted to the bright cells and lost the glyphs over the dark ones.
    """
    ratios = [contrast_ratio(FOREGROUND, colour) for colour in band()]
    assert max(ratios) / min(ratios) <= 1.7
    assert min(ratios) >= 3.0


def test_the_band_holds_enough_colours_to_build_a_palette_from():
    """Narrower bands read better and collapse to one hue.

    At width .10 the cube offers three families — red, blue, violet — and every
    session looks the same. Anchors alone do not have to cover teal or green:
    `dither` mixes those from pairs. But there must be enough anchors to mix.
    """
    assert len(band()) >= 8
    assert len(families()) >= 3
    assert sum(len(f) for f in families()) == len(band())


def test_a_family_groups_shades_of_one_hue():
    for members in families():
        assert len({family_of(colour) for colour in members}) == 1
    assert len({hex_to_oklch(f[0]).h // 60 for f in families()}) == len(families())
