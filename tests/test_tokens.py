"""Token taxonomy tests: own | reserved | transient."""
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    NodeType,
)
from dandelion.domain.tokens import finalize_token_roles


def _tok(addr_byte: str, membership: str, iface_erc20: bool = True) -> ContractNode:
    n = ContractNode(address="0x" + addr_byte * 20, chain_id=1,
                     node_type=NodeType.TOKEN, is_scope=False, membership=membership)
    if iface_erc20:
        n.notes.append("iface: approve, balanceOf, transfer, totalSupply")
    return n


def _build() -> ArchitectureGraph:
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    g.add_node(pool)
    own = _tok("aa", "member")          # own token (member)
    reserved = _tok("bb", "external")   # reserved asset (via getReservesList)
    transient = _tok("cc", "external")  # merely in the flows
    for n in (own, reserved, transient):
        g.add_node(n)
    # reserve asset arrived via an asset-getter from the pool
    g.add_edge(pool.key, reserved.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    # own — via a struct-getter (does not affect the role; membership decides the role)
    g.add_edge(pool.key, own.key, EdgeType.DEPENDS_ON, "getter:struct rewardToken()")
    # transient — via a flow (CALLS)
    g.add_edge(transient.key, pool.key, EdgeType.CALLS, "top caller")
    return g


def test_token_roles():
    g = _build()
    finalize_token_roles(g)
    assert g.get_node(1, "0x" + "aa" * 20).token_role == "own"
    assert g.get_node(1, "0x" + "bb" * 20).token_role == "reserved"
    assert g.get_node(1, "0x" + "cc" * 20).token_role == "transient"


def test_non_token_untouched():
    g = ArchitectureGraph()
    n = ContractNode(address="0x" + "05" * 20, chain_id=1, node_type=NodeType.ORACLE)
    g.add_node(n)
    finalize_token_roles(g)
    assert g.get_node(1, "0x" + "05" * 20).token_role is None


def test_reserved_dominates_membership_leak():
    # token is in the reserve list but accidentally marked member → still reserved (not own)
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    leak = _tok("ee", "member")   # membership leaked into member
    g.add_node(pool)
    g.add_node(leak)
    g.add_edge(pool.key, leak.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    finalize_token_roles(g)
    assert g.get_node(1, "0x" + "ee" * 20).token_role == "reserved"


def test_factory_instance_is_own_not_reserved():
    # own instance from the project's factory — even if it's also on an asset edge, it's own
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    atoken = _tok("ff", "member")
    g.add_node(pool)
    g.add_node(atoken)
    g.add_edge(pool.key, atoken.key, EdgeType.CREATED_BY, "factory event")
    g.add_edge(pool.key, atoken.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    finalize_token_roles(g)
    assert g.get_node(1, "0x" + "ff" * 20).token_role == "own"


def test_reserved_via_asset_even_if_proxy_type():
    # a reserve asset can be a proxy token (USDC=FiatToken proxy) — role by the asset edge
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    usdc = ContractNode(address="0x" + "dd" * 20, chain_id=1,
                        node_type=NodeType.PROXY, is_scope=False, membership="external")
    g.add_node(pool)
    g.add_node(usdc)
    g.add_edge(pool.key, usdc.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    finalize_token_roles(g)
    assert g.get_node(1, "0x" + "dd" * 20).token_role == "reserved"
