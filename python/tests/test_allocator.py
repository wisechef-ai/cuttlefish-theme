"""CONTRACT (packages/core/CONTRACT.md) §1: 20-slot identity allocator, hand-computed + golden + TS parity."""
import hashlib
import json
import random

import pytest

from cuttlefish_theme.python.domain import allocator as A

from .conftest import REPO

VECTORS = REPO / "packages" / "core" / "fixtures" / "identity-vectors.json"


def test_constants_and_hue_of_slot_are_exact():
    assert (A.ARC_START, A.ARC_END, A.SLOTS, A.STEP, A.CAP) == (110.0, 340.0, 20, 11.5, 3)
    assert A.hue_of_slot(0) == 115.75 and A.hue_of_slot(19) == 334.25 and A.hue_of_slot(7) == 110 + 11.5 * 7.5
    for bad in (-1, 20, 1.5, True, "3"):
        with pytest.raises(ValueError):
            A.hue_of_slot(bad)


def test_preferred_is_blake2b_256_first_8_bytes_big_endian_mod_20():
    for root in ("abc", "", "x", "日本語", "20261015_232342_2c978c", "😀" * 5):
        d = hashlib.blake2b(root.encode("utf-8"), digest_size=32).digest()
        want = int.from_bytes(d[:8], "big") % 20
        if root.strip():
            assert A.preferred(root) == want


def test_alone_takes_the_hash_slot():
    a = A.allocate("abc", [])
    assert (a.slot, a.hue_deg, a.crowded) == (A.preferred("abc"), A.hue_of_slot(A.preferred("abc")), False)


def test_empty_or_blank_root_is_an_error_never_a_guess():
    for r in ("", "   ", "\t\n"):
        with pytest.raises(ValueError):
            A.allocate(r, [])
        with pytest.raises(ValueError):
            A.preferred(r)


def test_peer_slots_outside_0_19_are_rejected():
    for bad in ([-1], [20], [1.5], [True]):
        with pytest.raises(ValueError):
            A.allocate("r", bad)


def test_far_enough_then_closest_to_hash_then_lowest_index():
    pref = A.preferred("abc")
    # one peer sitting on the hash slot: some free slot >= CAP away exists; nearest-to-hash among them wins
    got = A.allocate("abc", [pref]).slot
    far = [k for k in range(20) if abs(k - pref) >= 3]
    assert got == max(far, key=lambda k: (-abs(k - pref), -k))
    # every free slot is within CAP of a peer except none -> falls to closest-to-hash then lowest index
    peers = [k for k in range(20) if k % 3 == 0]
    free = [k for k in range(20) if k not in peers]
    want = max(free, key=lambda k: (min(3, min(abs(k - p) for p in peers)), -abs(k - pref), -k))
    assert A.allocate("abc", peers).slot == want


def test_full_house_repeats_the_hash_slot_and_surfaces_crowded():
    a = A.allocate("abc", list(range(20)))
    assert a.slot == A.preferred("abc") and a.crowded is True
    assert A.allocate("abc", list(range(20)) * 2).crowded is True


def test_free_slot_is_never_crowded_and_duplicates_and_order_do_not_matter():
    rnd = random.Random(3)
    peers = [2, 2, 9, 9, 9, 15]
    ref = A.allocate("lineage-x", peers)
    for _ in range(20):
        rnd.shuffle(peers)
        assert A.allocate("lineage-x", peers) == ref
    assert ref.crowded is False and ref.slot not in peers


def test_default_name_label_and_trim():
    d = hashlib.blake2b(b"abc", digest_size=32).hexdigest()
    assert A.default_name("abc") == "s-" + d[:4]
    assert A.trim_name("  " + "é" * 40 + "  ") == "é" * 16 and A.trim_name("   ") == ""


def test_golden_vectors_match_2101_of_2101():
    cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 2101
    bad = []
    for c in cases:
        a = A.allocate(c["lineage_root"], c["peers"])
        got = {"slot": a.slot, "hue_deg": round(a.hue_deg, 2), "crowded": a.crowded,
               "preferred": A.preferred(c["lineage_root"])}
        want = {k: c[k] for k in got}
        if got != want:
            bad.append((c["lineage_root"][:20], c["peers"], got, want))
    assert not bad, f"{len(bad)}/{len(cases)} mismatches, first: {bad[:2]}"
    print(f"\nVECTORS {len(cases) - len(bad)}/{len(cases)}")


def _random_cases(n, seed=2909):
    rnd = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789_-./ 日本語é😀\u0000"
    out = []
    for i in range(n):
        root = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 40)))
        if not root.strip():
            root = f"r{i}"
        peers = [rnd.randrange(20) for _ in range(rnd.choice([0, 0, 1, 2, 3, 5, 8, 12, 16, 19, 20, 24]))]
        out.append({"lineage_root": root, "peers": peers})
    return out


def test_10000_random_cases_are_identical_to_the_ts_bundle(ts):
    cases = _random_cases(10_000)
    got = ts("return input.map(c => { const a = core.allocate(c.lineage_root, c.peers);"
             " return [a.slot, a.hue_deg, a.crowded]; });", cases)
    assert len(got) == 10_000
    bad = [(c, g) for c, g in zip(cases, got)
           if (lambda a: [a.slot, a.hue_deg, a.crowded])(A.allocate(c["lineage_root"], c["peers"])) != g]
    assert not bad, f"{len(bad)}/10000 differ, first: {bad[:2]}"
    print(f"\nRANDOM {10_000 - len(bad)}/10000")
