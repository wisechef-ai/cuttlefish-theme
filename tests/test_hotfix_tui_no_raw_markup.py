"""HOTFIX-TUI (cf2909, PLAN-v22 s13.1).

Core TUI `ui-tui/src/banner.ts::parseRichMarkup` understands only `[#fg]..[/]`.
The per-cell `[#fg on #bg]` markup our hero/logo use is printed LITERALLY by
`hermes --tui`. Until core fix U5 lands, the skin writer must not emit
`banner_hero` / `banner_logo`; the TUI and CLI then fall back to stock art
painted in the skin's own colours.
"""
import yaml

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.pattern import render
from cuttlefish_theme.skinio import write_skin

CORPUS = [f"hotfix-session-{i}" for i in range(60)]


def test_skin_has_no_banner_markup_for_any_session(tmp_path):
    assert len(CORPUS) >= 50
    for sid in CORPUS:
        path = write_skin(render(allocate(sid)), hermes_home=tmp_path, name="cuttlefish")
        text = path.read_text()
        data = yaml.safe_load(text)
        for key in ("banner_hero", "banner_logo"):
            assert key not in data, f"{sid}: {key} written"
        # input_rule_art also uses `on #` but is not read by the TUI banner parser
        # (out of scope for this hotfix); only the banner keys are checked.
        for key in ("banner_hero", "banner_logo"):
            assert " on #" not in str(data.get(key, "")), f"{sid}: {key} markup"
        assert data["colors"], f"{sid}: colors must survive"
        assert "input_rule_art" in data  # unrelated key unchanged
