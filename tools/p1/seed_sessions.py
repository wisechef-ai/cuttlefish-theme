#!/usr/bin/env python3
"""Seed a THROWAWAY HERMES_HOME's state.db with the 20 P1 fixture sessions, so the real desktop sidebar
lists one row per fixture session and SESSION_ROW_AREAS hands our swatch each row's stored id (= the
fixture `lineage_id`).

Run it with the hermes-agent venv python (it imports `hermes_state` read-only from the checkout):

    HERMES_HOME=/tmp/x/hermes-home PYTHONDONTWRITEBYTECODE=1 \\
        ~/.hermes/hermes-agent/venv/bin/python tools/p1/seed_sessions.py --checkout ~/.hermes/hermes-agent

Refuses the live ~/.hermes. Prints one JSON line {db, sessions}.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True, help="hermes-agent checkout providing hermes_state (read-only)")
    ap.add_argument("--fixture", default=str(HERE / "stub-sessions.json"))
    ns = ap.parse_args(argv)
    home = os.environ.get("HERMES_HOME", "")
    live = Path(os.environ.get("HOME", "/home/adam")) / ".hermes"
    if not home or Path(home).resolve() == live.resolve():
        print("seed_sessions: HERMES_HOME must be a throwaway directory, not the live ~/.hermes", file=sys.stderr)
        return 2
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(ns.checkout).resolve()))
    from hermes_state import SessionDB  # noqa: E402  (import after the path is set)

    fx = json.loads(Path(ns.fixture).read_text())
    db_path = Path(home) / "state.db"
    db = SessionDB(db_path=db_path)
    now = time.time()
    try:
        # Oldest first, so the default newest-first sidebar lists idx 0 at the top.
        for s in reversed(fx["sessions"]):
            sid = s["lineage_id"]
            db.create_session(sid, "cli")
            db.set_session_title(sid, s["name"])
            db.append_message(sid, "user", f"cf2909 P1 stub session {s['name']}", timestamp=now - 600 + s["idx"] * -10)
            db.append_message(sid, "assistant", "ok", timestamp=now - 599 + s["idx"] * -10)
    finally:
        db.close()
    print(json.dumps({"db": str(db_path), "sessions": len(fx["sessions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
