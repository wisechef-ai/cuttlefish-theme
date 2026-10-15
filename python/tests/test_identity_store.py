"""identity.json: allocate on first hook, persist forever, lineage root from state.db (read-only)."""
import json
import random

from cuttlefish_theme.python import identity_store as I
from cuttlefish_theme.python.domain import allocator as A


def store(home, clock, **kw):
    return I.IdentityStore(home, clock=clock, **kw)


def read_identity(home):
    return json.loads((home / "cuttlefish" / "identity.json").read_text())


def test_first_hook_allocates_and_persists(home, clock):
    s = store(home, clock)
    ident = s.ensure("20261015_a", live_roots=lambda: set())
    assert ident.lineage_root == "20261015_a" and ident.allocated is True
    assert ident.hue_cd == A.allocate("20261015_a", []).hue_cd
    doc = read_identity(home)
    assert doc["schema"] == "cf2909.identity/1" and doc["rev"] >= 1
    e = doc["sessions"]["20261015_a"]
    assert e["hue_cd"] == ident.hue_cd and e["hue_deg"] == ident.hue_cd / 100
    assert e["allocated_at"] == clock() and e["name"].startswith("s-")


def test_persistence_second_allocation_with_different_peers_keeps_stored_hue(home, clock):
    s = store(home, clock)
    first = s.ensure("root-1", live_roots=lambda: set())
    # a brand-new process (no caches) now sees crowded peers
    for i in range(10):
        store(home, clock).ensure(f"peer-{i}", live_roots=lambda: set())
    again = store(home, clock).ensure("root-1", live_roots=lambda: {f"peer-{i}" for i in range(10)})
    assert again.hue_cd == first.hue_cd and again.allocated is False


def test_peers_are_the_stored_hues_of_live_roots_only(home, clock):
    s = store(home, clock)
    s.ensure("p1", live_roots=lambda: set())
    s.ensure("p2", live_roots=lambda: {"p1"})
    p1 = read_identity(home)["sessions"]["p1"]["hue_cd"]
    expect = A.allocate("me", [p1]).hue_cd
    assert s.ensure("me", live_roots=lambda: {"p1", "me"}).hue_cd == expect  # self is never a peer
    # p2 is not live -> not a peer
    s2 = store(home, clock)
    assert s2.ensure("me2", live_roots=lambda: {"p1"}).hue_cd == A.allocate("me2", [p1]).hue_cd


def test_order_independence_cold_warm_and_shuffled(home, clock):
    ids = [f"sess-{i}" for i in range(12)]
    live = set()
    first = {}
    warm = store(home, clock)
    for rid in ids:  # warm: one long-lived store allocates in arrival order
        first[rid] = warm.ensure(rid, live_roots=lambda: set(live)).hue_cd
        live.add(rid)
    for trial in range(3):  # cold + shuffled hook order: fresh process each time, same answers
        for rid in random.Random(trial).sample(ids, len(ids)):
            cold = I.IdentityStore(home, clock=clock).ensure(rid, live_roots=lambda: set(ids))
            assert cold.hue_cd == first[rid] and cold.allocated is False
            assert warm.ensure(rid, live_roots=lambda: set()).hue_cd == first[rid]
    assert len(set(first.values())) >= 8


def test_alone_in_any_order_gets_the_hash_slot(home, clock):
    assert store(home, clock).ensure("zzz", live_roots=lambda: set()).hue_cd == A.allocate("zzz", []).hue_cd


def test_rotation_unknown_child_resolves_to_known_root(home, clock, make_state_db):
    make_state_db(home, [("root", None, "My window"), ("child", "root", None), ("grandchild", "child", None)])
    s = store(home, clock)
    a = s.ensure("root", live_roots=lambda: set())
    b = store(home, clock).ensure("child", live_roots=lambda: {"root"})
    c = store(home, clock).ensure("grandchild", live_roots=lambda: {"root"})
    assert a.lineage_root == b.lineage_root == c.lineage_root == "root"
    assert a.hue_cd == b.hue_cd == c.hue_cd and b.allocated is False
    assert list(read_identity(home)["sessions"]) == ["root"]


def test_lineage_walk_caps_at_32_hops_and_survives_cycles(home, clock, make_state_db):
    rows = [(f"n{i}", f"n{i+1}", None) for i in range(60)] + [("n60", None, None)]
    make_state_db(home, rows)
    root = store(home, clock).lineage_root("n0")
    assert root == "n32"  # 32 hops, then stop
    make_state_db_cycle = home / "cyc"
    make_state_db_cycle.mkdir()
    make_state_db(make_state_db_cycle, [("a", "b", None), ("b", "a", None)])
    assert store(make_state_db_cycle, clock).lineage_root("a") in {"a", "b"}


def test_missing_db_table_or_row_means_root_is_the_id(home, clock, make_state_db):
    s = store(home, clock)
    assert s.lineage_root("x") == "x"  # no db
    import sqlite3
    sqlite3.connect(str(home / "state.db")).close()  # db without a table
    assert store(home, clock).lineage_root("x") == "x"
    h2 = home / "sub"
    h2.mkdir()
    make_state_db(h2, [("other", None, None)])
    assert store(h2, clock).lineage_root("x") == "x"  # no row
    # parent points at a row that was deleted: stop at the last known id
    h3 = home / "sub3"
    h3.mkdir()
    make_state_db(h3, [("kid", "gone", None)])
    assert store(h3, clock).lineage_root("kid") == "gone"


def test_state_db_is_opened_read_only_and_never_modified(home, clock, make_state_db):
    make_state_db(home, [("r", None, "t")])
    before = (home / "state.db").read_bytes()
    store(home, clock).ensure("r", live_roots=lambda: set())
    assert (home / "state.db").read_bytes() == before
    assert not list(home.glob("state.db-*"))  # no journal/wal litter


def test_name_comes_from_session_title_else_hash_label(home, clock, make_state_db):
    make_state_db(home, [("t1", None, "   A very long session title indeed   "), ("t2", None, ""), ("t3", None, None)])
    s = store(home, clock)
    s.ensure("t1", live_roots=lambda: set())
    n1 = read_identity(home)["sessions"]["t1"]["name"]
    assert n1 == "A very long sess" and len(n1) == 16
    assert s.ensure("t2", live_roots=lambda: set()).name == A.default_name("t2")
    assert s.ensure("t3", live_roots=lambda: set()).name == A.default_name("t3")


def test_hash_label_upgrades_to_title_once_the_title_exists(home, clock, make_state_db):
    make_state_db(home, [("late", None, None)])
    s = store(home, clock)
    assert s.ensure("late", live_roots=lambda: set()).name == A.default_name("late")
    import sqlite3
    con = sqlite3.connect(str(home / "state.db"))
    con.execute("update sessions set title='Named now' where id='late'")
    con.commit()
    con.close()
    clock.advance(120)
    ident = store(home, clock).ensure("late", live_roots=lambda: set())
    assert ident.name == "Named now" and ident.hue_cd == A.allocate("late", []).hue_cd


def test_sweep_drops_old_entries_and_caps_at_512(home, clock):
    s = store(home, clock)
    s.ensure("old", live_roots=lambda: set())
    clock.advance(31 * 86400)
    s.ensure("new", live_roots=lambda: set())
    s.sweep()
    assert list(read_identity(home)["sessions"]) == ["new"]
    doc = read_identity(home)
    for i in range(600):
        doc["sessions"][f"bulk-{i}"] = {"hue_cd": 11179, "hue_deg": 111.79, "name": "n",
                                        "allocated_at": clock(), "last_seen": clock() - i}
    (home / "cuttlefish" / "identity.json").write_text(json.dumps(doc))
    store(home, clock).sweep()
    kept = read_identity(home)["sessions"]
    assert len(kept) == 512 and "bulk-599" not in kept and "bulk-0" in kept


def test_corrupt_identity_file_does_not_break_allocation(home, clock):
    d = home / "cuttlefish"
    d.mkdir()
    (d / "identity.json").write_text("{not json")
    assert store(home, clock).ensure("r", live_roots=lambda: set()).hue_cd == A.allocate("r", []).hue_cd
