"""Shared fixtures: every test runs against a throwaway HERMES_HOME, never ~/.hermes."""
import os
import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "hermes-home"
    h.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(h))
    return h


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


@pytest.fixture
def clock():
    return Clock()


def _make_state_db(home, rows):
    """rows: [(id, parent_session_id, title)] -> <home>/state.db with a sessions table."""
    import sqlite3
    con = sqlite3.connect(str(home / "state.db"))
    con.execute("create table sessions (id text primary key, parent_session_id text, title text)")
    con.executemany("insert into sessions values (?,?,?)", rows)
    con.commit()
    con.close()


@pytest.fixture
def make_state_db():
    return _make_state_db
