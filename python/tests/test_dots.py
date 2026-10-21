"""D2 scatter oracle (python/domain/dots.py): behaviour of the 3 states added to the preview's 5
(review, unknown, degraded) plus the purity/determinism the TS port relies on.

Asserts on what is painted (cells, rgb), never on source text."""
import json

from cuttlefish_theme.python.domain import dots as D

from .conftest import REPO

COLS, ROWS = 64, 24
SEED = "s1"
HUE = 200.0


def cells(state, t=3.0, hue=HUE, seed=SEED, cols=COLS, rows=ROWS, entered=1000.0):
    return D.render(seed, hue, state, cols, rows, entered, [entered + t])[0]


def oklab_chroma(rgb):
    """Chroma of an sRGB triple in OKLab (0 for a pure grey)."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = map(lin, rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return (a * a + bb * bb) ** 0.5


def test_review_is_a_static_mottle_of_mid_expansion_organs():
    a, b = cells("review", 3.0), cells("review", 9.0)
    assert a == b, "review holds: no motion"
    glyphs = [c[2] for c in a]
    assert len(a) > 20 and len(set(glyphs)) >= 2, "blotches: more than one expansion level"
    assert all(c[4] == "id" for c in a), "identity pigment only: no alarm colours in review"
    # e is held in 0.2..0.7 -> never the full disc, never invisible
    assert "\u25cf" not in glyphs or glyphs.count("\u25cf") < len(glyphs) // 2


def test_review_blotches_are_spatially_coherent():
    by = {(c[0], c[1]): c[2] for c in cells("review", 3.0, cols=120, rows=24)}
    near = [(by[p], by[q]) for p in by for q in by if p < q and abs(p[0] - q[0]) <= 3 and abs(p[1] - q[1]) <= 2]
    far = [(by[p], by[q]) for p in by for q in by if p < q and abs(p[0] - q[0]) >= 40]
    same = lambda xs: sum(a == b for a, b in xs) / max(1, len(xs))
    assert same(near) > same(far), "neighbours agree more than distant organs: mottle, not salt"


def test_unknown_and_degraded_are_static_grey_with_no_hue():
    for state in ("unknown", "degraded"):
        a, b = cells(state, 2.0), cells(state, 8.0)
        assert a == b and a, state
        assert all(oklab_chroma(c[3]) < 0.004 for c in a), f"{state}: C 0, an identity colour leaked"
        assert {c[4] for c in a} == {"grey"}


def test_degraded_ignores_the_hue_it_is_given_unknown_with_a_hue_is_still_grey():
    assert cells("degraded", hue=120.0) == cells("degraded", hue=300.0) == cells("degraded", hue=None)
    assert cells("unknown", hue=120.0) == cells("unknown", hue=300.0)


def test_identity_states_carry_the_session_hue_unknown_does_not():
    warm, cool = cells("idle", hue=130.0), cells("idle", hue=300.0)
    assert [(c[0], c[1]) for c in warm] == [(c[0], c[1]) for c in cool], "positions never depend on hue"
    assert [c[3] for c in warm] != [c[3] for c in cool]
    assert all(oklab_chroma(c[3]) > 0.03 for c in warm)


def test_no_state_ever_leaves_the_identity_arc_unless_it_is_an_alarm():
    for state in D.STATES:
        for c in cells(state, 3.0):
            if c[4] == "id":
                assert oklab_chroma(c[3]) > 0.0 or state == "unknown"


def test_positions_are_fixed_per_seed_and_sparse():
    a = [(o.x, o.y) for o in D.constellation("s1", COLS, ROWS)]
    assert a == [(o.x, o.y) for o in D.constellation("s1", COLS, ROWS)]
    assert a != [(o.x, o.y) for o in D.constellation("s2", COLS, ROWS)]
    assert 0.02 < len(a) / (COLS * ROWS) < 0.10


def test_render_is_pure_same_arguments_same_cells_and_snapshots_are_independent():
    one = D.render(SEED, HUE, "tool", COLS, ROWS, 5.0, [6.0, 7.0])
    two = D.render(SEED, HUE, "tool", COLS, ROWS, 5.0, [7.0])
    assert one[1] == two[0], "a snapshot does not depend on which earlier snapshots were asked for"
    assert D.render(SEED, HUE, "tool", COLS, ROWS, 5.0, [6.0, 7.0]) == one


def test_tool_flashes_peak_with_the_pale_glint_and_thinking_never_does():
    peak = [c for t in (0.3, 0.6, 0.9, 1.2) for c in cells("tool", t)]
    assert any(c[4] == "glint" for c in peak)
    assert not any(c[4] == "glint" for t in (0.3, 0.6, 0.9, 1.2) for c in cells("thinking", t))


def test_fault_blanches_then_only_red_remains_and_needs_you_pulses_amber():
    assert {c[4] for c in cells("fault", 0.2)} <= {"id", "red"}
    assert {c[4] for c in cells("fault", 3.0)} == {"red"}
    pig = {c[4] for c in cells("needs-you", 3.0)}
    assert "amber" in pig and "red" not in pig


def test_the_golden_vector_file_is_exactly_what_the_oracle_writes():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen-dots-vectors.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_vectors_cover_every_state_scale_and_enough_scenes():
    v = json.loads((REPO / "packages" / "core" / "fixtures" / "dots-vectors.json").read_text())
    sc = v["scenes"]
    assert len(sc) >= 2000
    assert {s["state"] for s in sc} == set(D.STATES) | {"degraded"}
    assert {s["scale"] for s in sc} == {"XL", "M", "S"}
    assert len({s["seed"] for s in sc}) >= 3
    assert len({s["t"] for s in sc}) >= 4
