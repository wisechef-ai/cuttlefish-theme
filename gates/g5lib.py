"""Pure parts of the G5 blind-vision gate: strict answer parsing, thresholds, confusion matrix, round counter.

Thresholds mirror tools/p1/CONTRACT.md section 5 (frozen). An unparseable, refused or out-of-range answer is an
invalid answer: it counts as a FAIL for that item and is never skipped.
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

LABELS = ("idle", "working", "review", "needs input", "error", "unknown")
STATE_TO_LABEL = {"idle": "idle", "working": "working", "review": "review", "needs-you": "needs input",
                  "fault": "error", "unknown": "unknown", "degraded": "unknown"}
LETTERS = "ABCDEFGHIJKLMNOP"

AESTHETIC_MEDIAN_MIN, AESTHETIC_ITEM_MIN = 7.0, 6.0
LEGEND_ACCURACY_MIN = 0.80
IDENTITY_MIN_CORRECT = 14
KILL_RULE_ROUNDS = 3


@dataclass
class Answer:
    valid: bool
    value: object = None
    error: str = ""


def _json_object(text: str):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    for cand in [t] + re.findall(r"\{[^{}]*\}", t):
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_answer(text: str, task: str) -> Answer:
    """task: 'score' (0..10), 'label' (one of LABELS), 'match' (one letter A..P)."""
    obj = _json_object(text)
    if obj is None:
        return Answer(False, None, "no JSON object in the answer")
    if task == "score":
        v = obj.get("score")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 10:
            return Answer(False, None, f"score not a number in 0..10: {v!r}")
        return Answer(True, float(v) if isinstance(v, float) else v)
    if task == "label":
        v = obj.get("label")
        v = re.sub(r"\s+", " ", v.strip().lower().replace("_", " ").replace("-", " ")) if isinstance(v, str) else v
        return Answer(True, v) if v in LABELS else Answer(False, None, f"label not in legend: {v!r}")
    if task == "match":
        v = obj.get("match")
        v = v.strip().upper() if isinstance(v, str) else v
        return Answer(True, v) if isinstance(v, str) and len(v) == 1 and v in LETTERS else Answer(False, None, f"match not a tile letter: {v!r}")
    raise ValueError(f"unknown task {task!r}")


def seeded_shuffle(items, seed: int) -> list:
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


def sample_per_cell(items, cap: int, cell_of, label_of) -> list:
    """Keep at most ``cap`` items per cell, taking labels round-robin so every label stays represented. Order is preserved."""
    cells: dict = {}
    for n, it in enumerate(items):
        cells.setdefault(cell_of(it), {}).setdefault(label_of(it), []).append(n)
    picked = set()
    for by_label in cells.values():
        queues, taken = [list(v) for v in by_label.values()], 0
        while taken < cap and any(queues):
            for q in queues:
                if q and taken < cap:
                    picked.add(q.pop(0))
                    taken += 1
    return [it for n, it in enumerate(items) if n in picked]


# ---- verdicts -------------------------------------------------------------------------------
def aesthetic_verdict(scores: list) -> dict:
    """Pass: median >= 7 and no item < 6. A None (invalid answer) fails the direction."""
    invalid = sum(1 for s in scores if s is None)
    good = [s for s in scores if s is not None]
    med = statistics.median(good) if good else None
    mn = min(good) if good else None
    ok = bool(scores) and invalid == 0 and med is not None and mn is not None and med >= AESTHETIC_MEDIAN_MIN and mn >= AESTHETIC_ITEM_MIN
    return {"pass": ok, "median": med, "min": mn, "n": len(scores), "invalid": invalid}


def input_error_swaps(pairs) -> int:
    return sum(1 for t, p in pairs if (t, p) in (("needs input", "error"), ("error", "needs input")))


def legend_verdict(pairs: list) -> dict:
    """pairs = [(truth, predicted-or-None)]. Pass: accuracy >= 80 % and INPUT<->ERROR confusions == 0."""
    n = len(pairs)
    correct = sum(1 for t, p in pairs if p is not None and t == p)
    swaps = input_error_swaps(pairs)
    acc = correct / n if n else 0.0
    return {"pass": n > 0 and acc >= LEGEND_ACCURACY_MIN and swaps == 0, "accuracy": acc, "n": n, "correct": correct,
            "invalid": sum(1 for _, p in pairs if p is None), "input_error_confusions": swaps}


def identity_verdict(preds: list, truths: list) -> dict:
    correct = sum(1 for p, t in zip(preds, truths) if p is not None and p == t)
    return {"pass": correct >= IDENTITY_MIN_CORRECT, "correct": correct, "n": len(truths),
            "invalid": sum(1 for p in preds if p is None)}


def confusion_matrix(pairs: list) -> dict:
    cols = list(LABELS) + ["invalid"]
    counts = {t: {c: 0 for c in cols} for t in LABELS}
    for t, p in pairs:
        counts[t][p if p in LABELS else "invalid"] += 1
    return {"labels": list(LABELS), "columns": cols, "counts": counts}


def confusion_markdown(cm: dict) -> str:
    hot = {("needs input", "error"), ("error", "needs input")}
    head = "| truth \\ answered | " + " | ".join(cm["columns"]) + " |"
    rows = [head, "|---|" + "---|" * len(cm["columns"])]
    for t in cm["labels"]:
        cells = []
        for c in cm["columns"]:
            n = cm["counts"][t][c]
            cells.append((f"**{n}**" + (" ⚠" if n else "")) if (t, c) in hot else str(n))
        rows.append(f"| {t} | " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n\nINPUT↔ERROR cells (needs input→error, error→needs input) are bold; they must be 0."


# ---- kill-rule counter ----------------------------------------------------------------------
def record_round(path, direction: str, passed: bool, now: str | None = None, **extra) -> dict:
    """Append one G5 run to the rounds file; report the trailing consecutive failures for that direction."""
    import datetime as _dt
    p = Path(path)
    rounds = json.loads(p.read_text()) if p.exists() else []
    rounds.append({"direction": direction, "pass": bool(passed), "timestamp": now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **extra})
    p.write_text(json.dumps(rounds, indent=2) + "\n")
    streak = 0
    for r in reversed([r for r in rounds if r["direction"] == direction]):
        if r["pass"]:
            break
        streak += 1
    return {"direction": direction, "consecutive_failing_rounds": streak, "kill_rule_triggered": streak >= KILL_RULE_ROUNDS,
            "rounds_recorded": len(rounds)}
