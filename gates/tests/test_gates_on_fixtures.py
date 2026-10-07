"""The instruments proven on a known-good and a known-bad throwaway direction (synthetic renders through fixture_render.py)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_render  # noqa: E402
import g2  # noqa: E402
import g5  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the direction modules")

PLANTED = {"CONTRAST_AUTHORED", "CONTRAST_RENDERED", "IDENTITY_DELTA_E_16", "IDENTITY_DELTA_E_20",
           "IDENTITY_ALARM_ARC_16", "IDENTITY_ALARM_ARC_20", "STATIC_NONWORKING_CHANGES"}


@pytest.fixture(scope="module")
def renders(tmp_path_factory):
    root = tmp_path_factory.mktemp("renders")
    return {d: fixture_render.build(FIXTURES / d, root / d) for d in ("good", "bad")}


def test_g2_passes_the_good_direction(renders):
    assert g2.main([str(renders["good"])]) == 0
    r = json.loads((renders["good"].parent / "g2.json").read_text())
    assert r["pass"] and r["defects"] == []
    assert r["identity"]["grids"]["16"]["worst_delta_e"] >= 0.020 and r["identity"]["grids"]["20"]["worst_delta_e"] >= 0.020
    assert r["contrast_rendered"]["worst"]["ratio"] >= 4.5
    assert (renders["good"].parent / "g2.md").read_text().startswith("# G2: good: PASS")


def test_g2_fails_the_bad_direction_and_names_every_planted_defect(renders):
    assert g2.main([str(renders["bad"])]) == 1
    r = json.loads((renders["bad"].parent / "g2.json").read_text())
    assert not r["pass"]
    assert PLANTED <= {d["code"] for d in r["defects"]}
    md = (renders["bad"].parent / "g2.md").read_text()
    assert all(code in md for code in PLANTED)


def test_g2_writes_cvd_simulations_next_to_the_manifest(renders):
    root = renders["good"].parent
    for kind in ("deutan", "protan", "tritan"):
        assert (root / "cvd" / kind / "tui" / "M-half-tc-120-fault-t000.png").is_file()


class Scripted:
    """A backend that sees only (png, prompt), as the real ones do."""
    def __init__(self, legend='{"label": "idle"}', score='{"score": 8}', match='{"match": "A"}'):
        self.seen, self.legend, self.score, self.match = [], legend, score, match

    def __call__(self, png, prompt):
        assert Path(png).is_file() and Path(png).stat().st_size > 0
        self.seen.append(prompt)
        if '"label"' in prompt:
            return self.legend
        return self.score if '"score"' in prompt else self.match


def test_g5_pipeline_scores_saves_raw_and_counts_rounds(renders, tmp_path):
    a, b = Scripted(), Scripted(legend="I refuse", score="no")
    rounds = tmp_path / "rounds.json"
    rep = g5.run(renders["bad"], {"a": a, "b": b}, seed=7, workers=2, rounds_file=rounds, limit=60)
    assert rep["items"] == 60 and not rep["pass"]
    assert rep["per_backend"]["b"]["invalid_or_failed_calls"] >= 55          # refusals are counted, never skipped
    assert rep["per_backend"]["b"]["legend"]["accuracy"] == 0.0
    assert not rep["per_backend"]["a"]["checks"]["legend"]                   # always "idle" cannot reach 80 %
    raw = list((renders["bad"].parent / "g5_raw" / "a").glob("*.json"))
    assert len(raw) == 60 and json.loads(raw[0].read_text())["prompt"]
    assert json.loads(rounds.read_text())[0]["direction"] == "bad" and rep["round"]["consecutive_failing_rounds"] == 1
    assert "Legend confusion matrix" in g5.to_markdown(rep)


def test_g5_prompts_sent_to_models_carry_no_design_vocabulary(renders):
    a, b = Scripted(), Scripted()
    g5.run(renders["good"], {"a": a, "b": b}, seed=3, rounds_file=None, limit=40)
    sent = " ".join(a.seen + b.seen).lower()
    assert sent
    for word in ("cuttlefish", "sepia", "chromatophore", "mantle", "needs-you", "fault", "iridophore"):
        assert word not in sent


def test_legend_task_masks_text_by_default_and_keeps_alarm_words_on_request(renders):
    import numpy as np
    import dirtools
    import g5items
    import gatelib
    man, ddir = gatelib.load_manifest(renders["bad"]), dirtools.resolve_direction_dir("bad")

    def sample(keep):
        items = {i.id: i for i in g5items.legend_items(man, ddir, "M", None, keep)}
        return np.asarray(items["legend-M-plain-M-half-256-120-needs-you-t000"].image)

    masked, kept = sample(False), sample(True)
    assert masked.shape == kept.shape and not np.array_equal(masked, kept)   # the INPUT/ERROR words are the only difference
