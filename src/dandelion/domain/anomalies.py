"""
Structural risk anomalies — pure core (no I/O).

A reconstructed graph carries exactly the facts an auditor scans for first: who can upgrade,
who holds the keys, where funds sit, what is unverified. This turns those facts into a ranked
"look here" list — deterministically, from the graph alone, so it is universal and never a
hallucination. (An LLM may later explain/rank these; detection stays deterministic.)
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import ArchitectureGraph, ContractNode, EdgeType, NodeType, ProxyKind, SourceTier

# severity order for ranking
_SEV = {"high": 3, "medium": 2, "low": 1}


@dataclass
class Anomaly:
    key: str            # node key the finding anchors to
    kind: str           # short slug
    severity: str       # high | medium | low
    detail: str         # one-line human explanation


def _authority_addrs(node: ContractNode) -> set[str]:
    out: set[str] = set()
    if node.admin:
        out.add(node.admin)
    for r in node.roles:
        if r.holder:
            out.add(r.holder)
    return out


def _is_eoa(graph: ArchitectureGraph, addr: str) -> bool:
    for n in graph.nodes.values():
        if n.address == addr:
            return n.node_type == NodeType.EOA
    return False


def _has_safe_controller(graph: ArchitectureGraph, node: ContractNode) -> bool:
    """A multisig/timelock controls the node (governance handover, not a single key)."""
    auth = _authority_addrs(node)
    for n in graph.nodes.values():
        if n.address in auth and n.node_type in (NodeType.MULTISIG, NodeType.TIMELOCK):
            return True
    return False


def detect_anomalies(graph: ArchitectureGraph) -> list[Anomaly]:
    """Deterministic audit-relevant findings, ranked high→low."""
    out: list[Anomaly] = []
    custodial = {e.src for e in graph.edges if e.edge_type == EdgeType.HOLDS_FUNDS}

    for k, n in graph.nodes.items():
        if n.membership != "member":
            continue
        eoa_authority = any(_is_eoa(graph, a) for a in _authority_addrs(n))
        safe = _has_safe_controller(graph, n)

        # upgradeable contract whose only controller is a single EOA key
        if n.proxy_kind != ProxyKind.NONE and eoa_authority and not safe:
            out.append(Anomaly(k, "upgrade-single-key", "high",
                               "upgradeable proxy controlled by an EOA (no multisig/timelock)"))
        # a fund-custodying contract under single-key control
        if k in custodial and eoa_authority and not safe:
            out.append(Anomaly(k, "custody-single-key", "high",
                               "contract holds funds and is controlled by an EOA"))
        # a member core CONTRACT with no verified source (an EOA has no source, so skip it)
        if (n.node_type != NodeType.EOA
                and n.source_tier in (SourceTier.BYTECODE_ONLY, SourceTier.DECOMPILED)):
            out.append(Anomaly(k, "unverified-core", "medium",
                               f"member contract with {n.source_tier.value} source only"))
        # a member with no authority and no deployer link — unclustered / possibly mislabeled
        if not _authority_addrs(n) and not n.deployer and not n.is_scope:
            out.append(Anomaly(k, "orphan-member", "low",
                               "member with no authority or deployer link (verify membership)"))

    out.sort(key=lambda a: _SEV.get(a.severity, 0), reverse=True)
    return out
