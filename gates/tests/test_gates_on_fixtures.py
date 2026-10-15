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
    # anchor_guard off: this test scores a backend that refuses everything; with the guard on it is refused before scoring (below)
    rep = g5.run(renders["bad"], {"a": a, "b": b}, seed=7, workers=2, rounds_file=rounds, limit=60, anchor_guard=False)
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


def test_legend_text_policy_follows_d_r2_5_and_overrides_work(renders):
    import numpy as np
    import dirtools
    import g5items
    import gatelib
    man, ddir = gatelib.load_manifest(renders["bad"]), dirtools.resolve_direction_dir("bad")

    def sample(cvd, keep):
        items = {i.id: i for i in g5items.legend_items(man, ddir, "M", cvd, keep)}
        return np.asarray(items[f"legend-M-{cvd or 'plain'}-M-half-256-120-needs-you-t000"].image)

    kept, masked = sample(None, True), sample(None, False)
    assert kept.shape == masked.shape and not np.array_equal(kept, masked)          # the alarm words are the only difference
    assert np.array_equal(sample(None, None), kept)                                  # default plain = alarm text kept
    for cvd in ("deutan", "protan", "tritan"):                                       # CVD default = masked (pattern-only)
        a = sample(cvd, None)
        assert np.array_equal(a, sample(cvd, False)) and not np.array_equal(a, sample(cvd, True))


BLIND = '{"score": 0, "reason": "The image was unavailable, so its resemblance to living animal skin could not be assessed."}'


def _cache_files(root):
    return sorted(Path(root).rglob("*.json"))


def test_a_blind_backend_is_refused_before_scoring_and_nothing_is_cached(renders, tmp_path):
    import g5cache
    blind, sighted = Scripted(score=BLIND), Scripted(score='{"score": 9}')
    rounds, cache = tmp_path / "rounds.json", g5cache.Cache(tmp_path / "cache")
    with pytest.raises(g5.BlindBackend, match="anchor probe"):
        g5.run(renders["good"], {"blind": blind, "sighted": sighted}, seed=3, workers=2, rounds_file=rounds, limit=40, cache=cache)
    n_photos = len(g5.g5items.anchor_items())
    assert n_photos >= 3 and len(blind.seen) == n_photos          # only the probe was spent, never the other items
    assert sighted.seen == []                                     # refused before the next backend runs
    assert _cache_files(tmp_path / "cache") == []                 # no blind answer is cached
    assert not rounds.exists()                                    # no kill-rule round is recorded


def test_blind_answers_already_in_the_cache_are_still_refused(renders, tmp_path):
    import g5backends
    import g5cache
    cache = g5cache.Cache(tmp_path / "cache")
    g5.run(renders["good"], {"a": Scripted(score=BLIND), "b": Scripted()}, seed=3, rounds_file=None, limit=10, cache=g5cache.Cache(tmp_path / "x", enabled=False), anchor_guard=False)
    # poison: put blind anchor answers into the cache under backend "a", as the 2026-10-15 codex run did
    for it in g5.g5items.anchor_items():
        png = renders["good"].parent / "g5_raw" / "images" / f"{it.id}.png"
        it.image.save(png)
        cache.put(g5cache.key("a", g5backends.cache_model("a"), png, it.prompt), BLIND)
    fresh = Scripted(score='{"score": 9}')
    with pytest.raises(g5.BlindBackend, match="served from cache"):
        g5.run(renders["good"], {"a": fresh, "b": Scripted()}, seed=3, rounds_file=None, limit=10, cache=cache)
    assert fresh.seen == []                                       # every probe answer came from the poisoned cache


def test_a_sighted_run_records_the_probe_and_commits_its_cache(renders, tmp_path):
    import g5cache
    a, b = Scripted(score='{"score": 9}'), Scripted(score='{"score": 8}')
    rep = g5.run(renders["good"], {"a": a, "b": b}, seed=3, rounds_file=None, limit=12, cache=g5cache.Cache(tmp_path / "cache"))
    assert rep["anchor_probe"]["a"]["ok"] and rep["anchor_probe"]["a"]["median"] == 9 and rep["anchor_probe"]["b"]["median"] == 8
    n_photos = len(g5.g5items.anchor_items())
    probe_extra = n_photos - sum(1 for r in rep["per_backend"]["a"]["anchor_photos"]["scores"])
    assert len(_cache_files(tmp_path / "cache")) == 2 * (12 + probe_extra)
    assert "Anchor probe" in g5.to_markdown(rep)
