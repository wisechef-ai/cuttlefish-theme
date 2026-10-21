"""setup / uninstall / doctor / legend: surfaces are optional, symlinked, ledgered, and reported honestly."""
import json
import os

from cuttlefish_theme.python import doctor, legend, setup_cmd, surfaces


def fake_pkg(tmp_path, with_files):
    root = tmp_path / "pkg"
    for rel in with_files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// x\n")
    (root / "skins").mkdir(parents=True, exist_ok=True)
    return root


ALL = ("tui/cuttlefish.mjs", "desktop/plugin.js", "cli/cuttlefish_widget.py")


def mk_setup(home, pkg, loader_ok):
    out = []
    s = setup_cmd.Setup(home, pkg_root=pkg, out=out.append, tty=False,
                        loader=lambda: (loader_ok, "ok" if loader_ok else "core has no cli-widgets loader"))
    return s, out


def test_absent_artifacts_report_not_in_this_build_and_do_not_fail(home, tmp_path):
    pkg = fake_pkg(tmp_path, ())
    s, out = mk_setup(home, pkg, False)
    s.surfaces()
    text = "\n".join(out)
    assert text.count("not in this build") == 3
    for sf in surfaces.SURFACES:
        assert not surfaces.dest(home, sf).exists()


def test_present_artifacts_are_symlinked_and_ledgered_and_uninstall_undoes_them(home, tmp_path):
    pkg = fake_pkg(tmp_path, ALL)
    s, out = mk_setup(home, pkg, True)
    s.surfaces()
    for sf in surfaces.SURFACES:
        d = surfaces.dest(home, sf)
        assert d.is_symlink() and os.readlink(d) == str(pkg / sf.link_src)
    led = json.loads((home / "cuttlefish" / "ledger.json").read_text())
    assert len(json.dumps(led).split("symlink")) - 1 >= 3
    # idempotent
    s2, out2 = mk_setup(home, pkg, True)
    s2.surfaces()
    assert "already linked" in "\n".join(out2)
    u_out = []
    setup_cmd.Uninstall(home, out=u_out.append, poke=lambda *a, **k: None).run(keep_plugin=True)
    for sf in surfaces.SURFACES:
        assert not surfaces.dest(home, sf).is_symlink()


def test_classic_cli_is_not_linked_when_the_core_lacks_the_loader(home, tmp_path):
    pkg = fake_pkg(tmp_path, ALL)
    s, out = mk_setup(home, pkg, False)
    s.surfaces()
    assert not surfaces.dest(home, surfaces.by_id("classic-cli")).exists()
    assert "UNAVAILABLE: core has no cli-widgets loader" in "\n".join(out)


def test_foreign_file_at_the_destination_is_left_alone(home, tmp_path):
    pkg = fake_pkg(tmp_path, ALL)
    d = surfaces.dest(home, surfaces.by_id("tui"))
    d.parent.mkdir(parents=True)
    d.write_text("mine")
    s, out = mk_setup(home, pkg, True)
    s.surfaces()
    assert d.read_text() == "mine" and not d.is_symlink()


def report(home, pkg, loader_ok):
    return doctor.Doctor(home, pkg_root=pkg, env={}, loader=lambda: (loader_ok, "no loader")).report()


def surface_rows(rep):
    return {r["surface"]: r for r in rep["rows"] if r.get("kind") == "surface"}


def test_doctor_has_one_row_per_surface_with_reason_fix_and_tool_signal(home, tmp_path):
    rows = surface_rows(report(home, fake_pkg(tmp_path, ()), False))
    assert set(rows) == {"tui", "desktop", "classic-cli"}
    for r in rows.values():
        assert r["status"] == "UNAVAILABLE" and r["detail"] and r["how_to_fix"]
        assert r["tool_signal"] == "unknown"


def test_doctor_available_after_setup_and_classic_cli_unavailable_without_loader(home, tmp_path):
    pkg = fake_pkg(tmp_path, ALL)
    mk_setup(home, pkg, True)[0].surfaces()
    rows = surface_rows(report(home, pkg, True))
    assert {k: v["status"] for k, v in rows.items()} == {"tui": "AVAILABLE", "desktop": "AVAILABLE", "classic-cli": "AVAILABLE"}
    rows = surface_rows(report(home, pkg, False))
    assert rows["classic-cli"]["status"] == "UNAVAILABLE" and "no loader" in rows["classic-cli"]["detail"]


def test_doctor_json_is_valid_and_schema_tagged(home, tmp_path):
    out = []
    doctor.run(home, as_json=True, out=out.append, pkg_root=fake_pkg(tmp_path, ()), loader=lambda: (False, "x"))
    assert json.loads("\n".join(out))["schema"] == "cf2909.doctor/2"


def test_legend_covers_seven_states_plus_degraded_and_never_paints_a_background(capsys):
    out = []
    legend.run(out=out.append)
    text = "\n".join(out)
    for st in ("idle", "thinking", "tool", "review", "needs-you", "fault", "unknown", "degraded"):
        assert st in text
    assert "\x1b[48" not in text and "\x1b]11" not in text


def _uninstall(home):
    out = []
    setup_cmd.Uninstall(home, out=out.append, poke=lambda *a, **k: None).run(keep_plugin=True)
    return out


def _real_bus_record(home, root="root-a"):
    """A bus record exactly as the BusWriter emits it."""
    from cuttlefish_theme.python import bus
    from cuttlefish_theme.python.domain import reducer
    ev = reducer.normalise("pre_llm_call", {"session_id": "s"}, 1000.0)
    w = bus.BusWriter(home, clock=lambda: 1000.0, pid=1, host="h")
    w.record("sid-" + root, root, ev)
    return bus.paths.bus_file(home, root)


def _real_tmp_leftover(home, monkeypatch, d):
    """A temp file left behind by the REAL atomic writer (its replace fails mid-write)."""
    from cuttlefish_theme.python import bus
    monkeypatch.setattr(bus.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    monkeypatch.setattr(bus.os, "unlink", lambda *a: None)
    try:
        bus.atomic_write_json(d / "x.json", {"a": 1})
    except OSError:
        pass
    monkeypatch.undo()
    left = [p for p in d.iterdir() if p.name.startswith(".tmp-")]
    assert len(left) == 1
    return left[0]


def test_uninstall_preserves_unledgered_files_and_cleans_owned_state(home, monkeypatch):
    cf = home / "cuttlefish"
    (cf / "bus").mkdir(parents=True)
    for rel in ("identity.json", "identity.lock", "hooks.json", "state.json",
                "widget-heartbeat.json", "ledger.json"):
        (cf / rel).write_text("{}")
    rec = _real_bus_record(home)
    tmp_cf = _real_tmp_leftover(home, monkeypatch, cf)
    tmp_bus = _real_tmp_leftover(home, monkeypatch, cf / "bus")
    sentinel = cf / "user-notes.txt"
    sentinel.write_text("mine")
    nested = cf / "bus" / "keep.txt"
    nested.write_text("also mine")
    _uninstall(home)
    assert sentinel.read_text() == "mine" and nested.read_text() == "also mine"
    assert not rec.exists() and not tmp_cf.exists() and not tmp_bus.exists()
    assert sorted(p.relative_to(cf).as_posix() for p in cf.rglob("*") if p.is_file()) == [
        "bus/keep.txt", "user-notes.txt"]


def test_uninstall_preserves_files_that_only_match_our_name_patterns(home):
    """Review round 2: a name pattern is not proof of ownership."""
    cf = home / "cuttlefish"
    (cf / "bus").mkdir(parents=True)
    mine = {
        "cuttlefish/.tmp-personal-notes": "my notes",
        "cuttlefish/bus/.tmp-personal.json": '{"hello": "world"}',
        "cuttlefish/bus/unrecognized.json": '{"schema": "someone.else/1", "lineage_root": "unrecognized"}',
        "cuttlefish/bus/not-json.json": "not json at all",
        "cuttlefish/bus/looks-ours.json": '{"schema": "cf2909.bus/1"}',  # right schema, missing keys
    }
    for rel, body in mine.items():
        (home / rel).write_text(body)
    out = _uninstall(home)
    for rel, body in mine.items():
        assert (home / rel).read_text() == body, rel
        assert any(rel.split("/", 1)[1] in line and "untouched (not ours)" in line for line in out), rel
    assert (cf / "bus").is_dir() and cf.is_dir()  # dirs only go when empty


def test_uninstall_preserves_a_bus_record_filed_under_the_wrong_name(home):
    """Valid schema but not the file name our writer would give it -> not provably ours."""
    cf = home / "cuttlefish"
    rec = _real_bus_record(home, "root-a")
    other = rec.with_name("someone-elses-name.json")
    other.write_text(rec.read_text())
    _uninstall(home)
    assert other.exists() and not rec.exists()


def test_uninstall_removes_the_data_dir_when_only_owned_state_was_in_it(home, monkeypatch):
    cf = home / "cuttlefish"
    (cf / "bus").mkdir(parents=True)
    (cf / "ledger.json").write_text("{}")
    _real_bus_record(home, "r")
    _real_tmp_leftover(home, monkeypatch, cf / "bus")
    _real_tmp_leftover(home, monkeypatch, cf)
    _uninstall(home)
    assert not cf.exists()


def test_atomic_writer_temp_names_are_specific_and_match_the_uninstall_pattern(home, monkeypatch):
    from cuttlefish_theme.python import bus
    tmp = _real_tmp_leftover(home, monkeypatch, home)
    assert tmp.name.startswith(".tmp-cuttlefish-%d-" % os.getpid()) and tmp.name.endswith(".json")
    assert bus.is_our_tmp_name(tmp.name)
    for n in (".tmp-personal-notes", ".tmp-personal.json", ".tmp-cuttlefish-notes.json",
              ".tmp-cuttlefish-12-abc.json", "x.tmp-cuttlefish-12-abcdefgh.json"):
        assert not bus.is_our_tmp_name(n), n
