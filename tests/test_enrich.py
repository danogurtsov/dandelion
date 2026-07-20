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


# --- type hypotheses for unknown nodes (AI flexibility) --------------------- #
import asyncio  # noqa: E402

from dandelion.services.enrich import enrich_graph  # noqa: E402


class _FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    async def complete(self, messages, **kw):
        return self.payload


def test_llm_types_applied_only_to_unknown():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address="0x" + "11" * 20, chain_id=1, node_type=NodeType.UNKNOWN))
    g.add_node(ContractNode(address="0x" + "22" * 20, chain_id=1, node_type=NodeType.POOL))
    payload = ('{"types": [{"key": "1:0x' + "11" * 20 + '", "type": "oracle"}, '
               '{"key": "1:0x' + "22" * 20 + '", "type": "token"}]}')
    asyncio.run(enrich_graph(g, _FakeLLM(payload)))
    unk = g.get_node(1, "0x" + "11" * 20)
    assert unk.node_type == NodeType.ORACLE and unk.origin == "llm"       # unknown -> hypothesized
    assert any("llm-hypothesis" in n for n in unk.notes)
    # a node determinism already typed is NOT overwritten by the LLM
    assert g.get_node(1, "0x" + "22" * 20).node_type == NodeType.POOL


def test_llm_bogus_type_ignored():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address="0x" + "11" * 20, chain_id=1, node_type=NodeType.UNKNOWN))
    payload = '{"types": [{"key": "1:0x' + "11" * 20 + '", "type": "backdoor"}]}'
    asyncio.run(enrich_graph(g, _FakeLLM(payload)))
    assert g.get_node(1, "0x" + "11" * 20).node_type == NodeType.UNKNOWN   # not in vocab -> ignored
