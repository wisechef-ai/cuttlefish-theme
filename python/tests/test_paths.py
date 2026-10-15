from pathlib import Path

from cuttlefish_theme.python import paths as P


def test_hermes_home_env_wins_else_dot_hermes(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "x"))
    assert P.hermes_home() == tmp_path / "x"
    monkeypatch.delenv("HERMES_HOME")
    assert P.hermes_home() == Path.home() / ".hermes"
    monkeypatch.setenv("HERMES_HOME", "")
    assert P.hermes_home() == Path.home() / ".hermes"


def test_everything_lives_under_cuttlefish_dir(tmp_path):
    base = tmp_path / "cuttlefish"
    assert P.cuttlefish_dir(tmp_path) == base
    assert P.identity_file(tmp_path) == base / "identity.json"
    assert P.bus_dir(tmp_path) == base / "bus"
    assert P.bus_file(tmp_path, "a/..") == base / "bus" / "a_...json"


def test_safe_name_keeps_only_the_contract_charset():
    assert P.safe_name("Aa0._-") == "Aa0._-"
    assert P.safe_name("日本") == "__"
    assert P.safe_name("a b/c\\d") == "a_b_c_d"
