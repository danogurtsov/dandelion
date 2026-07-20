"""Validation membrane: executes AI actions, validates, superset-only, origin=llm."""
import asyncio

from dandelion.domain.actions import Action
from dandelion.domain.diagnostics import Diagnostics
from dandelion.domain.models import ArchitectureGraph, ContractNode, norm_addr
from dandelion.services.membrane import apply_actions

SEED = "0x" + "11" * 20
GOOD = "0x" + "22" * 20                               # a contract the getter returns
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"   # known-external
EOA = "0x" + "33" * 20                                # no code


def _word(a: str) -> str:
    return "0x" + "0" * 24 + a[2:]


class FakeRpc:
    def __init__(self, ret: str, codes: dict):
        self.ret, self.codes = ret, codes

    async def call(self, chain, to, data, *, from_=None, block=None):
        return self.ret

    async def get_code(self, chain, addr):
        return self.codes.get(norm_addr(addr), "0x")


def _graph():
    g = ArchitectureGraph()
    g.add_node(ContractNode(address=SEED, chain_id=1, is_scope=True))
    return g


def _run(action, ret, codes):
    g = _graph()
    diag = Diagnostics()
    disc = asyncio.run(apply_actions(g, FakeRpc(ret, codes), [action], diag=diag))
    return g, diag, disc


def test_valid_action_adds_llm_edge_and_lead():
    act = Action(key="1:" + norm_addr(SEED), kind="read_addr", sig="oracle()", purpose="struct")
    g, diag, disc = _run(act, _word(GOOD), {norm_addr(GOOD): "0x60code"})
    assert (1, norm_addr(GOOD)) in disc
    e = [e for e in g.edges if e.dst == "1:" + norm_addr(GOOD)]
    assert e and e[0].origin == "llm" and "getter:struct" in e[0].label
    assert diag.llm_rejected == 0


def test_known_external_rejected():
    act = Action(key="1:" + norm_addr(SEED), kind="read_addr", sig="weth()", purpose="asset")
    g, diag, disc = _run(act, _word(WETH), {norm_addr(WETH): "0x60code"})
    assert disc == [] and diag.llm_rejected == 1


def test_no_code_rejected():
    act = Action(key="1:" + norm_addr(SEED), kind="read_addr", sig="oracle()", purpose="struct")
    g, diag, disc = _run(act, _word(EOA), {})   # EOA has no code
    assert disc == [] and diag.llm_rejected == 1


def test_unknown_key_rejected():
    act = Action(key="1:0x" + "99" * 20, kind="read_addr", sig="oracle()")
    g, diag, disc = _run(act, _word(GOOD), {norm_addr(GOOD): "0x60"})
    assert disc == [] and diag.llm_rejected == 1


def test_membrane_is_superset_only():
    # existing deterministic nodes/edges are untouched; membrane only appends
    g = _graph()
    g.add_node(ContractNode(address="0x" + "44" * 20, chain_id=1))
    before_nodes = set(g.nodes)
    before_edges = list(g.edges)
    act = Action(key="1:" + norm_addr(SEED), kind="read_addr", sig="oracle()", purpose="struct")
    asyncio.run(apply_actions(g, FakeRpc(_word(GOOD), {norm_addr(GOOD): "0x60"}), [act]))
    assert before_nodes <= set(g.nodes)                # nodes only added (seed set unchanged)
    assert all(e in g.edges for e in before_edges)      # prior edges preserved
