"""CONTRACT §2 resolve order (model level) and the bus-entry reader (§5 entry -> resolved state)."""
from cuttlefish_theme.python.domain import resolve as R

NOW = 5000.0


def model(**kw):
    m = {"in_turn": False, "pending": [], "fault": False, "review_until": None, "finalized": False,
         "last_seen": NOW - 1, "bound": True, "pid_alive": None}
    m.update(kw)
    return m


def test_first_match_wins_in_contract_order():
    assert R.resolve(model(), NOW) == "idle"
    assert R.resolve(model(review_until=NOW + 0.1), NOW) == "review"
    assert R.resolve(model(review_until=NOW + 0.1, in_turn=True), NOW) == "working"
    assert R.resolve(model(in_turn=True, fault=True), NOW) == "fault"
    assert R.resolve(model(in_turn=True, fault=True, pending=["clarify:a"]), NOW) == "needs-you"
    for kw in ({"finalized": True}, {"pid_alive": False}, {"bound": False}, {"last_seen": None}, {"last_seen": NOW - 20.5}):
        assert R.resolve(model(pending=["clarify:a"], fault=True, in_turn=True, **kw), NOW) == "unknown"


def entry(**kw):
    e = {"state": "working", "owner_host": "box", "owner_pid": 42, "heartbeat": NOW - 2}
    e.update(kw)
    return e


def res(e, alive=True, host="box", now=NOW):
    return R.resolve_entry(e, now=now, this_host=host, pid_alive=lambda pid: alive)


def test_entry_fresh_live_resolves_to_its_state():
    assert res(entry()) == "working" and res(entry(state="needs-you")) == "needs-you"


def test_entry_missing_malformed_or_finalized_is_unknown():
    assert res(None) == "unknown" and res({"state": "working"}) == "unknown"
    assert res(entry(heartbeat="soon")) == "unknown" and res(entry(state="bogus")) == "unknown"
    assert res(entry(state="unknown")) == "unknown"


def test_entry_stale_after_20s_even_when_pid_lives():
    assert R.STALE_S == 20.0
    assert res(entry(heartbeat=NOW - 20.5)) == "unknown"
    assert res(entry(heartbeat=NOW - 20)) == "working"


def test_entry_dead_pid_on_this_host_is_unknown_but_remote_pid_is_not_probed():
    assert res(entry(), alive=False) == "unknown"
    probed = []
    out = R.resolve_entry(entry(owner_host="other"), now=NOW, this_host="box",
                          pid_alive=lambda pid: probed.append(pid) or False)
    assert out == "working" and probed == []


def test_entry_review_pulse_expires_at_review_until():
    e = entry(state="review", review_until=NOW + 0.3)
    assert res(e) == "review" and res(e, now=NOW + 0.3) == "idle"
