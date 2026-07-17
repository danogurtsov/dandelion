"""
Token taxonomy — pure core (no I/O). A post-pass over the graph.

Not all tokens are equal. For on-chain research it matters to DISTINGUISH a token's role:
  • own       — a PROJECT token (issued/controlled by it): aToken/debtToken/gov/LP-share.
                Signal: the token node is recognized as a member (project authority/factory/proxy).
  • reserved  — an explicitly RESERVED/accepted asset: reserve-list, whitelisted-collateral —
                something the protocol OPERATES ON (accepts as a deposit). Signal: reached via
                an asset enumeration (getReservesList/getAllReservesTokens → getter:asset edge).
  • transient — merely flowing in/out through traces (co-occurrence/CALLS), neither owned nor reserved.

Reserved assets are part of the project's surface (they must be KNOWN in full), even though their
code is external.
"""
from __future__ import annotations

from .models import ArchitectureGraph, ContractNode, EdgeType, NodeType


def _is_tokenish(n: ContractNode) -> bool:
    """Node behaves like an ERC token: by type or by an ERC20 interface in notes."""
    if n.node_type == NodeType.TOKEN:
        return True
    iface = " ".join(n.notes).lower()
    return "transfer" in iface and "balanceof" in iface


def _reached_via_asset_getter(graph: ArchitectureGraph, k: str) -> bool:
    """Node arrived as an enumerated asset (reserve-list) → getter:asset edge into it."""
    return any(
        e.dst == k and e.edge_type == EdgeType.DEPENDS_ON and "getter:asset" in e.label
        for e in graph.edges
    )


def _factory_created(graph: ArchitectureGraph, k: str) -> bool:
    """Node created by a project factory (CREATED_BY factory) → an OWN instance, not an external asset."""
    return any(
        e.dst == k and e.edge_type == EdgeType.CREATED_BY and "factory" in e.label
        for e in graph.edges
    )


def _impl_of_reserved_proxy(graph: ArchitectureGraph, k: str) -> bool:
    """Is the node the logic (impl) of a reserved proxy? Then it is external-asset code → also reserved."""
    for e in graph.edges:
        if e.dst == k and e.edge_type == EdgeType.IS_PROXY_FOR:
            src = e.src
            if _reached_via_asset_getter(graph, src) and not _factory_created(graph, src):
                return True
    return False


def is_reserved_asset(graph: ArchitectureGraph, k: str) -> bool:
    """
    An explicitly RESERVED asset: reached via an asset enumeration (reserve-list) — OR is the
    impl of such a reserved proxy (USDC=FiatToken proxy+impl) — and NOT created by a project factory.
    Dominates the membership heuristics: if a pool accepts a token as a deposit, it is reserved
    (external code, part of the surface), even if something else references it or its impl.
    Own instances (aToken from a factory) do not fall under this.
    """
    if _factory_created(graph, k):
        return False
    return _reached_via_asset_getter(graph, k) or _impl_of_reserved_proxy(graph, k)


def finalize_token_roles(graph: ArchitectureGraph) -> None:
    """Assign token_role to token-like nodes (own | reserved | transient)."""
    for k, n in graph.nodes.items():
        reserved = is_reserved_asset(graph, k)
        if not (_is_tokenish(n) or reserved):
            continue
        if reserved:                        # a reserve asset dominates the member heuristic
            n.token_role = "reserved"
        elif n.membership == "member":
            n.token_role = "own"
        else:
            n.token_role = "transient"
