"""Every recorded TUI trace, replayed by the Python reducer, equals the TS bundle's replayJson (CONTRACT §2/§4).

The TS side is generated here via node from tui/core.bundle.mjs: no duplicated expected files are committed."""
import json

import pytest

from cuttlefish_theme.python.domain import replay as RP

from .conftest import TRACES


def _tui_traces():
    out = []
    for p in sorted(TRACES.glob("*.jsonl")):
        head = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
        if head.get("host") == "tui":
            out.append(p)
    return out


TUI = _tui_traces()


def test_there_are_11_tui_traces():
    assert len(TUI) == 11, [p.name for p in TUI]


@pytest.mark.parametrize("path", TUI, ids=lambda p: p.stem)
def test_python_replay_equals_the_ts_bundle(path, ts):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    want = json.loads(ts("return core.replayJson(input);", lines))
    got = RP.replay(lines)
    assert got == want
    assert sum(len(r["samples"]) for r in want["roots"].values()) > 0   # not vacuous


def test_replay_reaches_every_hook_state_across_the_tui_traces():
    seen = set()
    for p in TUI:
        for r in RP.replay(p.read_text(encoding="utf-8").splitlines())["roots"].values():
            seen |= {s["state"] for s in r["samples"]}
    assert seen == {"idle", "working", "review", "needs-you", "fault", "unknown"}


def test_replay_rejects_a_trace_without_a_header_and_a_line_without_t():
    with pytest.raises(ValueError):
        RP.replay(['{"v":1,"t":1,"src":"hook","kind":"pre_llm_call","session":"s"}'])
    hdr = '{"v":1,"src":"meta","kind":"trace","host":"tui","name":"x"}'
    with pytest.raises(ValueError):
        RP.replay([hdr, '{"src":"hook","kind":"pre_llm_call","session":"s"}'])
    with pytest.raises(ValueError):
        RP.replay([hdr], step_s=0)


def test_lines_with_neither_root_nor_session_are_counted_not_guessed():
    hdr = '{"v":1,"src":"meta","kind":"trace","host":"tui","name":"x"}'
    out = RP.replay([hdr, '{"t":1,"src":"hook","kind":"pre_llm_call","profile":"A"}'])
    assert out["skipped"] == 1 and out["roots"] == {}
