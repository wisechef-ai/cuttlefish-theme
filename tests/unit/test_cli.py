"""Unit: cuttlefish.cli — hermes cuttlefish doctor|skin|legend."""

from __future__ import annotations

import argparse

import pytest
from cuttlefish_theme.cuttlefish import cli, skin


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def run_cli(argv):
    parser = argparse.ArgumentParser(prog="cuttlefish")
    cli.setup_parser(parser)
    return cli.run(parser.parse_args(argv))


def test_doctor_reports_version_config_and_clean_state(home, capsys):
    assert run_cli(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "cuttlefish-theme 2.0.0" in out and str(home / "config.yaml") in out
    assert "warnings: none" in out and "not installed" in out


def test_doctor_surfaces_config_warnings(home, capsys):
    (home / "config.yaml").write_text("plugins:\n  entries:\n    cuttlefish-theme:\n      settings: {motion: wild}\n")
    assert run_cli(["doctor"]) == 0
    assert "[enum] motion" in capsys.readouterr().out


def test_skin_installs_and_removes(home, capsys):
    assert run_cli(["skin"]) == 0
    assert skin.skin_target(home).is_file()
    assert "display.skin cuttlefish" in capsys.readouterr().out, "we tell the user, we never select it"
    assert (home / "config.yaml").exists() is False, "install never writes config"
    assert run_cli(["skin", "--remove"]) == 0
    assert not skin.skin_target(home).exists()


def test_legend_teaches_the_language(home, capsys):
    assert run_cli(["legend"]) == 0
    out = capsys.readouterr().out
    for word in ("resting", "working", "needs_you", "error", "finished_unseen",
                 "mottle", "clouds", "zebra", "blanch", "eyespot",
                 "plugins.entries.cuttlefish-theme.settings"):
        assert word in out, word


def test_default_action_is_doctor(home, capsys):
    assert run_cli([]) == 0
    assert "cuttlefish-theme 2.0.0" in capsys.readouterr().out


def test_doctor_reports_an_installed_skin(home, capsys):
    target = skin.install(home)
    assert run_cli(["doctor"]) == 0
    assert f"installed at {target}" in capsys.readouterr().out


def test_skin_action_without_a_remove_flag_installs(home, capsys):
    """A Namespace straight from core's wiring may lack our flag entirely."""
    assert cli.run(argparse.Namespace(action="skin")) == 0
    assert "installed" in capsys.readouterr().out
    assert skin.skin_target(home).is_file()
