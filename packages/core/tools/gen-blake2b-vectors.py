#!/usr/bin/env python3
"""Generate fixtures/blake2b-vectors.json: expected BLAKE2b digests from Python hashlib.

Seeded, but the case LIST is only stable per Python version, so CI uses `--check`: it re-derives every
committed digest from hashlib instead of regenerating the file. The TS port in domain/blake2b.ts is tested against this file.
Cases: 240 random strings incl. non-ASCII / astral / empty, each at digest_size 32 and
a spread of other digest sizes (1..64), plus the RFC 7693 appendix-A vector.
"""
import hashlib, json, random, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "blake2b-vectors.json"
rng = random.Random(2909)
ALPHABETS = [
    "abcdefghijklmnopqrstuvwxyz0123456789_-",
    "ąćęłńóśźżÄÖÜßéèñçøå",
    "日本語のテキスト中文字符한국어",
    "😀🐙🦑🌊\U0001F9A0",
    "αβγδ ΩΨ кириллица",
]
if "--check" in sys.argv:
    committed = json.loads(OUT.read_text(encoding="utf-8"))["cases"]
    bad = [c for c in committed if hashlib.blake2b(c["msg"].encode("utf-8"), digest_size=c["size"]).hexdigest() != c["digest"]]
    if bad or len(committed) < 200:
        sys.exit(f"blake2b-vectors.json: {len(bad)} stale digests, {len(committed)} cases")
    print(f"blake2b-vectors.json ok: {len(committed)} digests match hashlib")
    sys.exit(0)

cases = []
cases.append({"msg": "", "size": 32})
cases.append({"msg": "abc", "size": 64})
for i in range(240):
    n = rng.choice([0, 1, 2, 7, 15, 16, 31, 64, 127, 128, 129, 200, 257])
    alpha = "".join(rng.choice(ALPHABETS) for _ in range(rng.randint(1, 3)))
    msg = "".join(rng.choice(alpha) for _ in range(n))
    cases.append({"msg": msg, "size": 32})
# other digest sizes
for size in (1, 8, 20, 31, 33, 48, 64):
    for i in range(6):
        msg = "".join(rng.choice(ALPHABETS[rng.randrange(len(ALPHABETS))]) for _ in range(rng.randint(0, 300)))
        cases.append({"msg": msg, "size": size})
for c in cases:
    c["digest"] = hashlib.blake2b(c["msg"].encode("utf-8"), digest_size=c["size"]).hexdigest()
OUT.write_text(json.dumps({"schema": "cf2909.blake2b-vectors/1", "generator": "tools/gen-blake2b-vectors.py (python hashlib)",
                           "cases": cases}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
print(f"wrote {len(cases)} cases -> {OUT}")
