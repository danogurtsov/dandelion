"""Unit tests for the pure parts of the LLM pass (compact/parse), no network."""
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    NodeType,
    ProxyKind,
    Role,
)
from dandelion.services.enrich import compact_graph, parse_llm_json


def test_parse_json_plain():
    assert parse_llm_json('{"protocol": "x"}') == {"protocol": "x"}


def test_parse_json_fenced():
    text = '```json\n{"protocol": "Fluid", "labels": []}\n```'
    assert parse_llm_json(text)["protocol"] == "Fluid"


def test_parse_json_with_prose():
    text = 'Here is the analysis:\n{"protocol": "y"}\nHope that helps.'
    assert parse_llm_json(text) == {"protocol": "y"}


def test_parse_json_garbage():
    assert parse_llm_json("no json here") == {}


def test_compact_graph_shape():
    g = ArchitectureGraph()
    p = ContractNode(address="0x" + "a" * 40, chain_id=1, node_type=NodeType.PROXY,
                     proxy_kind=ProxyKind.EIP1967_TRANSPARENT, implementation="0x" + "b" * 40,
                     name="Proxy", roles=[Role("owner", "0x" + "c" * 40, "owner()")])
    g.add_node(p)
    g.add_node(ContractNode(address="0x" + "b" * 40, chain_id=1, name="Impl"))
    g.add_edge(p.key, "1:0x" + "b" * 40, EdgeType.IS_PROXY_FOR)
    out = compact_graph(g)
    assert "chains: [1]" in out
    assert "(Proxy)" in out and "type=proxy" in out
    assert "roles=[owner=" in out
    assert "-is_proxy_for->" in out
