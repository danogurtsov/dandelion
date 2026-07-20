"""Deterministic structural risk anomalies."""
from dandelion.domain.anomalies import detect_anomalies
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    NodeType,
    ProxyKind,
    Role,
    SourceTier,
)

PROXY = "0x" + "11" * 20
EOA_ADMIN = "0x" + "22" * 20
SAFE = "0x" + "33" * 20
TOKEN = "0x" + "44" * 20


def test_upgradeable_eoa_admin_is_high():
    g = ArchitectureGraph()
    p = ContractNode(address=PROXY, chain_id=1, is_scope=True,
                     proxy_kind=ProxyKind.EIP1967_TRANSPARENT, admin=EOA_ADMIN)
    g.add_node(p)
    g.add_node(ContractNode(address=EOA_ADMIN, chain_id=1, node_type=NodeType.EOA))
    a = detect_anomalies(g)
    assert any(x.kind == "upgrade-single-key" and x.severity == "high" for x in a)


def test_multisig_admin_is_not_flagged():
    g = ArchitectureGraph()
    p = ContractNode(address=PROXY, chain_id=1, is_scope=True,
                     proxy_kind=ProxyKind.EIP1967_TRANSPARENT, admin=SAFE)
    g.add_node(p)
    g.add_node(ContractNode(address=SAFE, chain_id=1, node_type=NodeType.MULTISIG))
    assert not any(x.kind == "upgrade-single-key" for x in detect_anomalies(g))


def test_custody_single_key_is_high():
    g = ArchitectureGraph()
    pool = ContractNode(address=PROXY, chain_id=1, is_scope=True, node_type=NodeType.POOL)
    pool.roles.append(Role("owner", EOA_ADMIN, "owner()"))
    g.add_node(pool)
    g.add_node(ContractNode(address=EOA_ADMIN, chain_id=1, node_type=NodeType.EOA))
    g.add_node(ContractNode(address=TOKEN, chain_id=1, node_type=NodeType.TOKEN))
    g.add_edge(pool.key, "1:" + TOKEN, EdgeType.HOLDS_FUNDS, "balanceOf>0")
    assert any(x.kind == "custody-single-key" and x.severity == "high"
               for x in detect_anomalies(g))


def test_unverified_core_is_medium():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address=PROXY, chain_id=1, is_scope=True,
                            source_tier=SourceTier.BYTECODE_ONLY))
    a = detect_anomalies(g)
    assert any(x.kind == "unverified-core" and x.severity == "medium" for x in a)


def test_external_nodes_not_flagged():
    g = ArchitectureGraph()
    ext = ContractNode(address=PROXY, chain_id=1, is_scope=False,
                       proxy_kind=ProxyKind.EIP1967_TRANSPARENT, admin=EOA_ADMIN,
                       source_tier=SourceTier.BYTECODE_ONLY)
    ext.membership = "external"
    g.add_node(ext)
    g.add_node(ContractNode(address=EOA_ADMIN, chain_id=1, node_type=NodeType.EOA))
    assert detect_anomalies(g) == []       # anomalies are about project members only
