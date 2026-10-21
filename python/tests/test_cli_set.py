"""`hermes cuttlefish set`: three prefs, anything else exits 2, writes are atomic."""
import json
import os

import pytest

from cuttlefish_theme.python import cli, paths, prefs


def run(home, *argv):
    out, err = [], []
    p = __import__("argparse").ArgumentParser()
    cli.setup_parser(p)
    rc = cli.run(p.parse_args(["set", *argv]), home=home, out=out.append, err=err.append)
    return rc, out, err


@pytest.mark.parametrize("key,val,stored", [("mantle", "off", "off"), ("mantle", "on", "on"), ("mantle", "1", 1),
                                            ("mantle", "2", 2), ("twinkle", "auto", "auto"), ("twinkle", "on", "on"),
                                            ("twinkle", "off", "off"), ("cells", "auto", "auto"),
                                            ("cells", "half", "half"), ("cells", "bg", "bg")])
def test_valid_values_are_stored(home, key, val, stored):
    rc, _, _ = run(home, key, val)
    assert rc == 0
    doc = json.loads(paths.prefs_file(home).read_text())
    assert doc["schema"] == "cf2909.prefs/1" and doc[key] == stored


@pytest.mark.parametrize("argv", [("cells", "braille"), ("dots", "braille"), ("dots", "blocks"), ("mantle", "3"),
                                  ("twinkle", "maybe"), ("colour", "red"), ("mantle",)])
def test_everything_else_exits_2_and_writes_nothing(home, argv):
    rc, _, err = run(home, *argv)
    assert rc == 2 and err
    assert not paths.prefs_file(home).exists()


def test_braille_is_gone_from_the_stored_schema(home):
    run(home, "cells", "half")
    assert "dots" not in json.loads(paths.prefs_file(home).read_text())
    paths.prefs_file(home).write_text(json.dumps({"schema": "cf2909.prefs/1", "cells": "braille", "dots": "braille"}))
    assert prefs.load(home)["cells"] == "auto"      # a stale value from the old schema never reaches a surface


def test_a_bad_value_leaves_earlier_prefs_intact(home):
    run(home, "mantle", "2")
    rc, _, _ = run(home, "mantle", "9")
    assert rc == 2 and prefs.load(home)["mantle"] == 2


def test_write_is_atomic_no_temp_residue_and_replace_not_truncate(home, monkeypatch):
    run(home, "cells", "bg")
    d = paths.cuttlefish_dir(home)
    assert sorted(os.listdir(d)) == ["state.json"]
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append((os.path.basename(a), os.path.basename(b))), real(a, b)))
    run(home, "cells", "half")
    assert len(seen) == 1 and seen[0][0].startswith(".tmp-") and seen[0][1] == "state.json"


def test_no_args_shows_current_values(home):
    rc, out, _ = run(home)
    assert rc == 0 and any(l.startswith("mantle") for l in out)


@pytest.mark.parametrize("env,on", [({}, True), ({"TMUX": "/tmp/x,1,0"}, False), ({"TERM_PROGRAM": "ghostty"}, False),
                                    ({"TERM": "xterm-ghostty"}, False), ({"CMUX_SOCKET": "x"}, False),
                                    ({"HERMES_REDUCED_MOTION": "1"}, False)])
def test_twinkle_auto_rules(env, on):
    assert prefs.twinkle_effective("auto", env)[0] is on


def test_explicit_on_wins_except_under_reduced_motion():
    assert prefs.twinkle_effective("on", {"TMUX": "1"})[0] is True
    assert prefs.twinkle_effective("on", {"HERMES_REDUCED_MOTION": "1"})[0] is False
    assert prefs.twinkle_effective("off", {})[0] is False
