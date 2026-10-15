#!/usr/bin/env python3
"""Record `compression-rotate`: rotating compression (compression.in_place=false). The session id changes with no hook announcing it;
the lineage root stays the same (parent link only in state.db).   python3 tools/traces/record/compression_rotate.py"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Recording  # noqa: E402

NOTES = "compression.in_place=false: /compress rotates the stored id (child.parent_session_id=old); hooks switch to the child on the next pre_llm_call"
CFG = "compression:\n  in_place: false\n  protect_last_n: 2\n  protect_first_n: 1\n  threshold: 0.5\n"

if __name__ == "__main__":
    with Recording("compression-rotate", notes=NOTES, extra_cfg={"A": CFG}) as rec:
        t = rec.open_tui("A")
        for i, msg in enumerate(["Reply with exactly: one", "Reply with exactly: two"] + [f"Write a 40 word sentence about the number {n}." for n in range(4)]):
            assert rec.turn(t, msg), f"turn {i}"
        t.line("/compress")
        assert t.wait_hook("post_auxiliary_call", n=1, timeout=300, aux_task="compression"), "compression summary never finished"
        rec.settle(t, quiet=10, timeout=60)
        assert rec.turn(t, "Reply with exactly: after"), "post-compress turn"
        ids = []
        for r in t.hooks():
            if r["hook"] == "pre_llm_call" and r["ids"]["session_id"] not in ids:
                ids.append(r["ids"]["session_id"])
        db = sqlite3.connect(f"file:{rec.homes['A']}/state.db?mode=ro", uri=True)
        rows = db.execute("select id, parent_session_id from sessions").fetchall()
        print("lineage ids seen by hooks:", ids, "db:", rows, flush=True)
        assert len(ids) >= 2 and any(par for _, par in rows), "compression did not rotate the id"
        rec.exit_tui(t)
