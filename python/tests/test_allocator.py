"""CONTRACT §1: hand-computed examples (integer arithmetic, no float)."""
import itertools
import random

from cuttlefish_theme.python.domain import allocator as A


def test_candidate_grid_endpoints_are_hand_computed():
    # 11000 + 23000*(2k+1)//128
    assert A.cand(0) == 11000 + 23000 // 128 == 11179
    assert A.cand(25) == 20164
    assert A.cand(52) == 29867
    assert A.cand(63) == 33820


def test_candidates_stay_inside_the_arc_and_ascend():
    c = [A.cand(k) for k in range(64)]
    assert c == sorted(set(c))
    assert 11000 < c[0] and c[-1] < 34000


def test_digest_is_unkeyed_blake2b_8_bytes():
    assert A.digest("abc").hex() == "d8bb14d833d59559"
    assert A.digest("").hex() == "e4a6a0577479b2b4"
    assert A.base_of("abc") == 0x59 & 63 == 25
    assert A.base_of("") == 0xB4 & 63 == 52


def test_circular_distance():
    assert A.dist(100, 35900) == 200
    assert A.dist(35900, 100) == 200
    assert A.dist(0, 18000) == 18000
    assert A.dist(5, 5) == 0


def test_alone_takes_the_hash_slot():
    a = A.allocate("abc", [])
    assert (a.k, a.hue_cd, a.base) == (25, 20164, 25)
    assert a.digest_hex == "d8bb14d833d59559"
    e = A.allocate("", [])
    assert (e.k, e.hue_cd) == (52, 29867)


def test_one_peer_picks_the_farthest_candidate():
    # peer at 20164: the arc's top end (33820, 13656 away) beats its bottom end (11179, 8985 away)
    assert A.allocate("abc", [20164]).hue_cd == 33820


def test_two_peers_pick_the_largest_remaining_gap():
    # between 20164 and 33820 the best is only 6828 away; below 20164, 11179 is 8985 away
    assert A.allocate("abc", [20164, 33820]).hue_cd == 11179


def test_matches_an_independent_brute_force_with_ties_to_smallest_j():
    rnd = random.Random(7)
    grid = [A.cand(k) for k in range(64)]
    for n in range(300):
        root = f"root-{n}"
        peers = [rnd.choice(grid) for _ in range(rnd.randint(1, 24))]
        base = A.base_of(root)
        best = max(range(64), key=lambda j: (min(A.dist(grid[(base + j) % 64], p) for p in peers), -j))
        assert A.allocate(root, peers).k == (base + best) % 64


def test_duplicates_and_peer_order_do_not_change_the_answer():
    peers = [A.cand(3), A.cand(30), A.cand(30), A.cand(55)]
    ref = A.allocate("lineage-x", peers).hue_cd
    rnd = random.Random(1)
    for _ in range(20):
        p = peers[:]
        rnd.shuffle(p)
        assert A.allocate("lineage-x", p).hue_cd == ref
    assert A.allocate("lineage-x", sorted(set(peers))).hue_cd == ref


def test_result_is_always_a_grid_candidate_and_unicode_ids_work():
    grid = {A.cand(k) for k in range(64)}
    for root in ["日本語", "ünï", "a\u0000b", "😀" * 5, " ", "x" * 500]:
        assert A.allocate(root, []).hue_cd in grid
        assert A.allocate(root, [A.cand(1), A.cand(2)]).hue_cd in grid


def test_default_name_label_and_trim():
    assert A.default_name("abc") == "s-d8bb"
    assert A.trim_name("  " + "é" * 40 + "  ") == "é" * 16
    assert A.trim_name("   ") == ""
