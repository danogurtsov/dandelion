"""
Membership scoring — pure core.

Cluster = project. Each candidate address accumulates weight from membership
signals; the sum decides member / candidate / external. Seeds are always
member (1.0).
"""
from __future__ import annotations

# weight of a project-membership signal.
# PRINCIPLE: CONTROL decides (who governs), not a reference/co-occurrence.
# Weak signals (reference/co-occurrence) on their own → only candidate: they also
# catch external dependencies (oracle/token) that the project merely consumes.
SIGNAL_WEIGHTS: dict[str, float] = {
    # STRONG — enough on their own to make a member (shared control / code ownership)
    "shared_admin": 0.7,         # same admin/multisig/timelock as the project
    "is_proxy_or_impl": 0.7,     # impl of a recognized project proxy
    "same_deployer": 0.6,        # shared (NON-public) deployer
    "multichain_mirror": 0.6,    # same project on another chain
    "role_holder": 0.55,         # holds a role/admin over a member (= project governance)
    "exposed_getter": 0.6,       # member exposes X via a view getter (system component) → member
    "factory_instance": 0.6,     # instance created by a member factory (Create* event) → member
    # WEAK — only candidate without confirmation by control
    "explicit_reference": 0.35,  # member references X (may be an external dependency!)
    "cooccurrence": 0.25,        # frequent neighbor in traces (lead)
    "shared_codehash": 0.15,     # same bytecode (may be a fork)
}

MEMBER_THRESHOLD = 0.55
CANDIDATE_THRESHOLD = 0.25


def membership_score(signals: set[str]) -> float:
    """Sum of weights of present signals, clamped to 0..1."""
    return min(1.0, sum(SIGNAL_WEIGHTS.get(s, 0.0) for s in signals))


def classify(score: float) -> str:
    if score >= MEMBER_THRESHOLD:
        return "member"
    if score >= CANDIDATE_THRESHOLD:
        return "candidate"
    return "external"
