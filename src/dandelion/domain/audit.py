"""
Membership audit — pure core (no I/O).

Over-inclusive membership ("better to over-check") is only a defensible policy if it is
MEASURED. This computes an automatable precision proxy: a node marked `member` is almost
certainly a false positive when it is known-external infra, a reserved asset the project
merely custodies, or a plain non-authority EOA pulled in by activity. Those are mechanically
detectable, so we can report a conservative lower bound on precision and a leak list a human
can eyeball. The number is allowed to be unflattering — that is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .labels import is_known_external
from .models import ArchitectureGraph, EdgeType, NodeType
from .tokens import is_reserved_asset


@dataclass
class MembershipAudit:
    total_members: int = 0
    leaked_members: int = 0
    precision_proxy: float = 1.0            # 1 - leaked/total (conservative lower bound)
    leaks: list[tuple[str, str, str]] = field(default_factory=list)  # (key, name, reason)
    by_membership: dict[str, int] = field(default_factory=dict)
    by_token_role: dict[str, int] = field(default_factory=dict)


def _leak_reason(graph: ArchitectureGraph, k: str) -> str | None:
    """Why a `member` node is likely a false positive, or None if it looks legitimate."""
    n = graph.nodes[k]
    if is_known_external(n.address):
        return "known-external infra marked member"
    if is_reserved_asset(graph, k):
        return "reserved asset marked member"
    # an EOA is externally-owned (an operator/signer key), not a project contract; membership
    # is about code, so a non-seed EOA marked member is a false positive (authority lives in edges)
    if n.node_type == NodeType.EOA and not n.is_scope:
        return "EOA marked member (operator key, not a project contract)"
    return None


def membership_audit(graph: ArchitectureGraph) -> MembershipAudit:
    """Compute the precision proxy + leak list over the graph's membership verdicts."""
    members = {k for k, n in graph.nodes.items() if n.membership == "member"}
    audit = MembershipAudit(total_members=len(members))
    for k in members:
        reason = _leak_reason(graph, k)
        if reason:
            audit.leaked_members += 1
            audit.leaks.append((k, graph.nodes[k].name or "?", reason))
    audit.precision_proxy = round(
        1.0 - audit.leaked_members / max(1, audit.total_members), 3)
    for n in graph.nodes.values():
        audit.by_membership[n.membership] = audit.by_membership.get(n.membership, 0) + 1
        if n.token_role:
            audit.by_token_role[n.token_role] = audit.by_token_role.get(n.token_role, 0) + 1
    return audit
