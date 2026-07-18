"""Membership audit: precision proxy + leak detection."""
from dandelion.domain.audit import membership_audit
from dandelion.domain.models import ArchitectureGraph, ContractNode, EdgeType, NodeType

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # known-external


def test_clean_graph_precision_one():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True))  # real member
    g.add_node(ContractNode(address="0x" + "02" * 20, chain_id=1, is_scope=True,
                            node_type=NodeType.POOL))
    au = membership_audit(g)
    assert au.total_members == 2 and au.leaked_members == 0
    assert au.precision_proxy == 1.0


def test_known_external_member_is_a_leak():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True))
    # WETH wrongly marked member (a leak the audit must catch)
    weth = ContractNode(address=WETH, chain_id=1, is_scope=False,
                        node_type=NodeType.TOKEN, name="WETH9")
    weth.membership = "member"
    g.add_node(weth)
    au = membership_audit(g)
    assert au.leaked_members == 1
    assert au.precision_proxy == 0.5   # 1 of 2 members leaked
    assert any("known-external" in reason for _, _, reason in au.leaks)


def test_reserved_asset_member_is_a_leak():
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    reserved = ContractNode(address="0x" + "aa" * 20, chain_id=1, is_scope=False,
                            node_type=NodeType.TOKEN, name="SomeReserve")
    reserved.membership = "member"   # wrongly member despite being a reserve asset
    g.add_node(pool)
    g.add_node(reserved)
    g.add_edge(pool.key, reserved.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    au = membership_audit(g)
    assert au.leaked_members == 1
    assert any("reserved asset" in reason for _, _, reason in au.leaks)


def test_eoa_member_is_always_a_leak():
    # any non-seed EOA marked member is a false positive (operator key, not a contract) —
    # even an authority EOA: its role lives in edges, but it is not a project contract
    g = ArchitectureGraph()
    pool = ContractNode(address="0x" + "01" * 20, chain_id=1, is_scope=True)
    admin = ContractNode(address="0x" + "ad" * 20, chain_id=1, is_scope=False,
                         node_type=NodeType.EOA)
    admin.membership = "member"
    g.add_node(pool)
    g.add_node(admin)
    g.add_edge(admin.key, pool.key, EdgeType.HOLDS_ROLE_OVER, "owner")
    au = membership_audit(g)
    assert au.leaked_members == 1
    assert any("EOA marked member" in reason for _, _, reason in au.leaks)


def test_seed_eoa_is_not_a_leak():
    # a deliberately-seeded EOA is fine (the user asked for it)
    g = ArchitectureGraph()
    g.add_node(ContractNode(address="0x" + "ad" * 20, chain_id=1, is_scope=True,
                            node_type=NodeType.EOA))
    au = membership_audit(g)
    assert au.leaked_members == 0
