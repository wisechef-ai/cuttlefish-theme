"""bus/<root>.json: atomic writes, monotonic seq, journal <= 32, heartbeat, bounded sweep."""
import json
import threading
import time

from cuttlefish_theme.python import bus as B
from cuttlefish_theme.python import paths as P
from cuttlefish_theme.python.domain import reducer as R


def ev(hook, ts, **kw):
    return R.normalise(hook, dict(session_id="s", **kw), ts)


def writer(home, clock, **kw):
    kw.setdefault("heartbeat_interval", 5.0)
    return B.BusWriter(home, clock=clock, pid=4242, host="box", **kw)


def read(home, root):
    return json.loads(P.bus_file(home, root).read_text())


def test_atomic_write_reader_never_sees_a_partial_file(tmp_path):
    target = tmp_path / "x.json"
    B.atomic_write_json(target, {"n": 0})
    stop, bad = threading.Event(), []

    def reader():
        while not stop.is_set():
            try:
                json.loads(target.read_text())
            except FileNotFoundError:
                bad.append("missing")
            except ValueError as e:
                bad.append(repr(e))

    t = threading.Thread(target=reader)
    t.start()
    for i in range(400):
        B.atomic_write_json(target, {"n": i, "pad": "x" * (200_000 if i % 2 else 10)})
    stop.set()
    t.join()
    assert bad == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]  # no tmp litter


def test_entry_has_the_cf2909_bus_1_shape(home, clock):
    w = writer(home, clock)
    w.record("durable-1", "root-1", ev("pre_llm_call", clock()))
    e = read(home, "root-1")
    assert e["schema"] == "cf2909.bus/1"
    assert e["profile_home"] == str(home) and e["durable_id"] == "durable-1" and e["lineage_root"] == "root-1"
    assert (e["owner_pid"], e["owner_host"]) == (4242, "box")
    assert e["state"] == "working" and e["since"] == clock() and e["source"] == "pre_llm_call"
    assert e["heartbeat"] == clock() and e["seq"] == 1 and len(e["journal"]) == 1


def test_seq_is_monotonic_and_journal_is_bounded(home, clock):
    w = writer(home, clock)
    for i in range(50):
        clock.advance(1)
        w.record("d", "r", ev("pre_llm_call" if i % 2 == 0 else "on_session_end", clock(), completed=True))
        assert read(home, "r")["seq"] == i + 1
    e = read(home, "r")
    assert len(e["journal"]) == 32 and e["journal"][-1]["ts"] == clock()


def test_file_name_replaces_unsafe_characters(home, clock):
    w = writer(home, clock)
    w.record("d", "a/b é.c-d", ev("pre_llm_call", clock()))
    assert [p.name for p in P.bus_dir(home).iterdir()] == ["a_b__.c-d.json"]


def test_new_process_continues_seq_and_reducer_state_from_the_file(home, clock):
    w = writer(home, clock)
    w.record("d", "r", ev("pre_llm_call", clock()))
    w.record("d", "r", ev("pre_tool_call", clock(), tool_name="clarify", tool_call_id="c1"))
    w2 = writer(home, clock)  # fresh process, same lineage
    e = w2.record("d", "r", ev("post_tool_call", clock(), tool_name="clarify", tool_call_id="c1"))
    assert e["seq"] == 3 and e["state"] == "working"


def test_rotation_updates_durable_id_in_the_same_file(home, clock):
    w = writer(home, clock)
    w.record("old", "root", ev("pre_llm_call", clock()))
    w.record("new", "root", ev("pre_llm_call", clock()))
    assert [p.name for p in P.bus_dir(home).iterdir()] == ["root.json"]
    assert read(home, "root")["durable_id"] == "new"


def test_heartbeat_thread_refreshes_without_new_events_and_is_single(home, clock):
    w = writer(home, clock, heartbeat_interval=0.05)
    w.record("d", "r", ev("pre_llm_call", clock()))
    w.start_heartbeat()
    w.start_heartbeat()
    assert sum(1 for t in threading.enumerate() if t.name == "cuttlefish-heartbeat") == 1
    t0 = clock()
    clock.advance(3)
    deadline = time.time() + 3
    while time.time() < deadline and read(home, "r")["heartbeat"] == t0:
        time.sleep(0.02)
    e = read(home, "r")
    w.stop()
    assert e["heartbeat"] == clock() and e["seq"] == 1 and e["state"] == "working"


def test_starting_the_heartbeat_never_blocks_a_hook(home, clock):
    w = writer(home, clock, heartbeat_interval=60)
    t = time.perf_counter()
    w.record("d", "r", ev("pre_llm_call", clock()))
    w.start_heartbeat()
    assert time.perf_counter() - t < 0.5
    w.stop()


def test_finalize_deletes_the_file_and_stops_refreshing(home, clock):
    w = writer(home, clock)
    w.record("d", "r", ev("pre_llm_call", clock()))
    w.record("d", "r", ev("on_session_finalize", clock()))
    assert not P.bus_file(home, "r").exists()
    w.refresh_heartbeats()
    assert not P.bus_file(home, "r").exists()


def test_bus_resumes_with_a_fresh_file_after_finalize_then_new_turn(home, clock):
    w = writer(home, clock)
    w.record("d", "r", ev("pre_llm_call", clock()))
    w.record("d", "r", ev("on_session_finalize", clock()))
    e = w.record("d", "r", ev("pre_llm_call", clock()))
    assert e["state"] == "working" and e["seq"] == 3


def test_sweep_removes_day_old_heartbeats_and_touches_at_most_64(home, clock):
    d = P.bus_dir(home)
    d.mkdir(parents=True)
    for i in range(100):
        (d / f"old{i}.json").write_text(json.dumps({"heartbeat": clock() - 90_000, "state": "idle"}))
    (d / "fresh.json").write_text(json.dumps({"heartbeat": clock() - 10, "state": "idle"}))
    (d / "junk.json").write_text("{nope")
    assert B.sweep(home, clock()) <= 64
    left = {p.name for p in d.iterdir()}
    assert "fresh.json" in left and len([n for n in left if n.startswith("old")]) >= 100 - 64
    while B.sweep(home, clock()):
        pass
    assert {p.name for p in d.iterdir()} <= {"fresh.json", "junk.json"}


def test_live_roots_excludes_stale_dead_and_unknown(home, clock):
    w = writer(home, clock)
    w.record("d", "alive", ev("pre_llm_call", clock()))
    w.record("d", "dead", ev("pre_llm_call", clock()))
    w.record("d", "stale", ev("pre_llm_call", clock() - 100))
    p = P.bus_file(home, "stale")
    e = json.loads(p.read_text())
    e["heartbeat"] = clock() - 100
    p.write_text(json.dumps(e))
    d = P.bus_file(home, "dead")
    e = json.loads(d.read_text())
    e["owner_pid"] = 7
    d.write_text(json.dumps(e))
    live = B.live_roots(home, now=clock(), this_host="box", pid_alive=lambda pid: pid != 7)
    assert live == {"alive"}
