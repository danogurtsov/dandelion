"""Unit tests for the pure M0 domain modules."""
from dandelion.domain.cooccurrence import rank_neighbors, strong_neighbors
from dandelion.domain.deployers import is_common_deployer
from dandelion.domain.membership import classify, membership_score
from dandelion.domain.multichain import detect_mirrors, is_mirror

A = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40


# --- deployers ---
def test_common_deployer_denylist():
    assert is_common_deployer("0x4e59b44847b379578588920ca78fbf26c0b4956c") is True
    assert is_common_deployer("0xBA5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed") is True  # case-insensitive
    assert is_common_deployer(A) is False
    assert is_common_deployer(None) is False


# --- cooccurrence ---
def test_rank_neighbors_counts_cooccurrence():
    traces = [
        [A, B, C],
        [A, B],
        [A, C],
        [B, C],       # without A — not counted
    ]
    ranked = rank_neighbors(traces, A)
    d = dict(ranked)
    assert d[B] == 2 and d[C] == 2
    assert ranked[0][1] == 2


def test_strong_neighbors_threshold():
    ranked = [(B, 10), (C, 1)]
    strong = strong_neighbors(ranked, min_count=3, min_ratio=0.2)
    assert B in strong and C not in strong


# --- multichain ---
def test_is_mirror_requires_codehash_match():
    assert is_mirror("0xdead", "0xDEAD") is True
    assert is_mirror("0xdead", "0xbeef") is False
    assert is_mirror(None, "0xdead") is False


def test_detect_mirrors():
    per = {10: "0xaaa", 8453: "0xaaa", 42161: "0xbbb", 137: None}
    assert set(detect_mirrors("0xAAA", per)) == {10, 8453}


# --- membership ---
def test_membership_scoring_and_classify():
    assert classify(membership_score({"is_proxy_or_impl"})) == "member"      # 0.7
    assert classify(membership_score({"cooccurrence"})) == "candidate"        # 0.3
    assert classify(membership_score(set())) == "external"                    # 0.0
    # multiple signals → clamped to 1.0
    assert membership_score({"shared_admin", "explicit_reference", "multichain_mirror"}) == 1.0
