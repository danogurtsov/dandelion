"""
Semantic relation typing — pure core (no I/O).

The crawl records that A depends on B, but a generic `DEPENDS_ON` loses the *meaning* of the
relation. A downstream reader (or an auditor) wants to know which dependencies are price feeds
and where funds are custodied. These are deterministically recoverable from what we already know
(the target's type / a balance read), so we type them instead of leaving `READS_PRICE_FROM` /
`HOLDS_FUNDS` as declared-but-unused edge kinds. Runs as a final refinement, after membership.
"""
from __future__ import annotations

from .models import ArchitectureGraph, EdgeType, NodeType

# node types that cannot custody value themselves (so we skip balanceOf reads on them)
_NON_CUSTODIAL = (NodeType.TOKEN, NodeType.ORACLE, NodeType.EOA)


def retype_oracle_reads(graph: ArchitectureGraph) -> int:
    """
    Retype DEPENDS_ON edges whose target is an oracle into READS_PRICE_FROM (label/origin kept).
    A price-feed dependency is the single most safety-relevant relation in a DeFi graph.
    """
    n = 0
    for e in graph.edges:
        if e.edge_type != EdgeType.DEPENDS_ON:
            continue
        dst = graph.nodes.get(e.dst)
        if dst is not None and dst.node_type == NodeType.ORACLE:
            e.edge_type = EdgeType.READS_PRICE_FROM
            n += 1
    return n


def custody_candidates(graph: ArchitectureGraph) -> list[tuple[str, str]]:
    """
    (holder_key, token_key) pairs to balance-check for HOLDS_FUNDS: a custodial member node and a
    token it references (reserve/own/transient). The service reads balanceOf(holder) on the token;
    a non-zero balance becomes a HOLDS_FUNDS edge. Pure enumeration; the I/O stays in the service.
    """
    token_keys = {k for k, n in graph.nodes.items()
                  if n.node_type == NodeType.TOKEN or n.token_role is not None}
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for e in graph.edges:
        if e.edge_type not in (EdgeType.DEPENDS_ON, EdgeType.READS_PRICE_FROM):
            continue
        holder = graph.nodes.get(e.src)
        if holder is None or holder.membership != "member":
            continue
        if holder.node_type in _NON_CUSTODIAL:   # a token/oracle/EOA does not custody the reserve
            continue
        if e.dst in token_keys and (e.src, e.dst) not in seen:
            seen.add((e.src, e.dst))
            out.append((e.src, e.dst))
    return out
