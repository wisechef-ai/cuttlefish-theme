"""CONTRACT §3: what a reader may show. Never the last known state."""
from cuttlefish_theme.python.domain import resolve as R

NOW = 5000.0


def entry(**kw):
    e = {"state": "working", "owner_host": "box", "owner_pid": 42, "heartbeat": NOW - 2}
    e.update(kw)
    return e


def res(e, alive=True, host="box", now=NOW):
    return R.resolve(e, now=now, this_host=host, pid_alive=lambda pid: alive)


def test_fresh_live_entry_resolves_to_its_state():
    assert res(entry()) == "working"
    assert res(entry(state="needs-you")) == "needs-you"


def test_missing_entry_is_unknown():
    assert res(None) == "unknown"


def test_stale_heartbeat_is_unknown_even_when_pid_lives():
    assert R.STALE_S == 30
    assert res(entry(heartbeat=NOW - 31)) == "unknown"
    assert res(entry(heartbeat=NOW - 30)) == "working"  # strictly greater than STALE_S


def test_dead_pid_on_this_host_is_unknown():
    assert res(entry(), alive=False) == "unknown"


def test_pid_is_not_probed_for_a_remote_owner():
    probed = []
    out = R.resolve(entry(owner_host="other"), now=NOW, this_host="box",
                    pid_alive=lambda pid: probed.append(pid) or False)
    assert out == "working" and probed == []


def test_finalized_entry_is_unknown():
    assert res(entry(state="unknown")) == "unknown"


def test_malformed_entry_is_unknown_not_an_exception():
    assert res({"state": "working"}) == "unknown"
    assert res(entry(heartbeat="soon")) == "unknown"
    assert res(entry(state="bogus")) == "unknown"
