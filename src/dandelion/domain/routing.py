"""
LLM routing — pure core (no I/O).

The ablation showed the LLM adds ~0 where determinism already wins. So we route it only to
nodes where determinism has stalled: no verified source (bytecode-only / decompiled), a type it
could not resolve, or a factory/singleton left un-enumerated. Everywhere else stays purely
deterministic — cheaper, and the LLM's measured value concentrates where it is real.
"""
from __future__ import annotations

from .models import ArchitectureGraph, ContractNode, EdgeType, NodeType, SourceTier


def is_opaque(node: ContractNode) -> bool:
    """A node where deterministic expansion has nothing to chew on."""
    return (
        node.source_tier in (SourceTier.BYTECODE_ONLY, SourceTier.DECOMPILED, SourceTier.ABSENT)
        or node.node_type == NodeType.UNKNOWN
    )


def opaque_keys(graph: ArchitectureGraph) -> list[str]:
    """Member/candidate nodes that are opaque or an un-enumerated factory — the LLM's targets."""
    created_from = {e.src for e in graph.edges
                    if e.edge_type == EdgeType.CREATED_BY and "factory" in e.label}
    out: list[str] = []
    for k, n in graph.nodes.items():
        if n.membership == "external":
            continue
        stalled = is_opaque(n)
        if n.node_type == NodeType.FACTORY and k not in created_from:
            stalled = True    # a factory whose instances were never enumerated
        if stalled:
            out.append(k)
    return out
