"""``ledger.json`` (CONTRACT §4): exactly what ``setup`` changed, written BEFORE each change, so ``uninstall``
restores only that. Entries are ordered; uninstall walks them in reverse and re-verifies each before undoing it."""
from . import bus, paths

SCHEMA = "cf2909.ledger/1"


def load(home):
    doc = bus.read_json(paths.ledger_file(home))
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        return {"schema": SCHEMA, "entries": []}
    return doc


def record(home, entry):
    """Append ``entry`` and persist it atomically. Call this before performing the change it describes."""
    doc = load(home)
    doc["schema"] = SCHEMA
    doc["entries"].append(entry)
    bus.atomic_write_json(paths.ledger_file(home), doc)
    return entry


def find(doc, op, **match):
    return [e for e in doc["entries"] if e.get("op") == op and all(e.get(k) == v for k, v in match.items())]
