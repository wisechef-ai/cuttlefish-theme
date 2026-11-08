#!/usr/bin/env python3
"""Re-sanitise committed evidence JSON with the rule of evidence_lib.ts scrubPath (dev only).

    python3 tools/desktop/scrub_evidence.py evidence/v2 evidence/v2-1280x800

The user home prefix becomes <home>/ and a tailnet-range address becomes <tailnet-ip>. Only JSON files that change are rewritten.
It refuses to touch any raw/ file (their sha256 are bound by the manifests): a hit there is reported and fails the run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOME = re.compile("/ho" + "me/" + r"[^/\s\"']+/")  # split so this file does not match itself
TAILNET = re.compile(r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")


def scrub_str(s: str) -> str:
    return TAILNET.sub("<tailnet-ip>", HOME.sub("<home>/", s))


def scrub(v):
    if isinstance(v, str):
        return scrub_str(v)
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items()}
    return v


def main(dirs: list[str]) -> int:
    changed, failed = [], []
    for d in dirs:
        for p in sorted(Path(d).rglob("*.json")):
            if "raw" in p.relative_to(d).parts:
                if json.dumps(scrub(json.loads(p.read_text()))) != json.dumps(json.loads(p.read_text())):
                    failed.append(str(p))
                continue
            before = json.loads(p.read_text())
            after = scrub(before)
            if after != before:
                p.write_text(json.dumps(after, indent=2) + "\n")
                changed.append(str(p))
    for p in changed:
        print("scrubbed", p)
    for p in failed:
        print("REFUSED (raw file, sha-bound):", p)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
