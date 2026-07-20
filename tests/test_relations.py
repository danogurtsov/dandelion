"""Semantic relation typing: oracle reads + custody candidates."""
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    NodeType,
)
from dandelion.domain.relations import custody_candidates, retype_oracle_reads

POOL = "0x" + "11" * 20
ORACLE = "0x" + "22" * 20
TOKEN = "0x" + "33" * 20
REGISTRY = "0x" + "44" * 20


def _graph():
    g = ArchitectureGraph()
    pool = ContractNode(address=POOL, chain_id=1, is_scope=True, node_type=NodeType.POOL)
    oracle = ContractNode(address=ORACLE, chain_id=1, node_type=NodeType.ORACLE)
    token = ContractNode(address=TOKEN, chain_id=1, node_type=NodeType.TOKEN)
    reg = ContractNode(address=REGISTRY, chain_id=1, node_type=NodeType.UNKNOWN)
    for n in (pool, oracle, token, reg):
        g.add_node(n)
    g.add_edge(pool.key, oracle.key, EdgeType.DEPENDS_ON, "getter:struct getPriceOracle()")
    g.add_edge(pool.key, token.key, EdgeType.DEPENDS_ON, "getter:asset getReservesList()")
    g.add_edge(pool.key, reg.key, EdgeType.DEPENDS_ON, "getter:struct registry()")
    return g


def test_oracle_edge_retyped():
    g = _graph()
    n = retype_oracle_reads(g)
    assert n == 1
    price = [e for e in g.edges if e.edge_type == EdgeType.READS_PRICE_FROM]
    assert len(price) == 1 and price[0].dst == "1:" + ORACLE
    # the non-oracle depends_on edges are untouched
    assert sum(1 for e in g.edges if e.edge_type == EdgeType.DEPENDS_ON) == 2


def test_custody_candidates_only_custodial_members_and_tokens():
    g = _graph()
    cands = custody_candidates(g)
    # pool (custodial member) -> token (tokenish) is a candidate; oracle/registry are not
    assert ("1:" + POOL, "1:" + TOKEN) in cands
    assert all(t != "1:" + ORACLE for _, t in cands)
    assert all(t != "1:" + REGISTRY for _, t in cands)


def test_non_member_holder_excluded():
    g = _graph()
    g.get_node(1, POOL).membership = "candidate"   # not a member → no custody edge
    assert custody_candidates(g) == []
