"""End-to-end test of deterministic reconstruction on FakeRpc (no network)."""
import asyncio

from dandelion.domain.models import EdgeType, NodeType, ProxyKind, node_key, norm_addr
from dandelion.domain.proxies import SLOT_1967_ADMIN, SLOT_1967_IMPL
from dandelion.services.reconstruct import reconstruct

A = "0x" + "a" * 40      # proxy (scope seed)
B = "0x" + "b" * 40      # implementation
ADMIN = "0x" + "c" * 40  # proxy admin (contract)
OWNER = "0x" + "d" * 40  # owner (EOA)
OWNER_SELECTOR = "0x8da5cb5b"  # owner()


def _word(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:]


class FakeRpc:
    def __init__(self):
        self.codes = {
            (1, norm_addr(A)): "0x6080proxy",
            (1, norm_addr(B)): "0x6080impl",
            (1, norm_addr(ADMIN)): "0x1234",
            (1, norm_addr(OWNER)): "0x",           # EOA
            (10, norm_addr(A)): "0x6080proxy",      # mirror on chain 10
        }
        self.storages = {
            (1, norm_addr(A), SLOT_1967_IMPL.lower()): _word(B),
            (1, norm_addr(A), SLOT_1967_ADMIN.lower()): _word(ADMIN),
        }
        self.calls = {(1, norm_addr(A), OWNER_SELECTOR): _word(OWNER)}
        self.codehashes = {
            (1, norm_addr(A)): "0xaaa",
            (1, norm_addr(B)): "0xbbb",
            (1, norm_addr(ADMIN)): "0xccc",
            (10, norm_addr(A)): "0xaaa",             # same codehash → mirror
        }

    async def get_code(self, chain, addr):
        return self.codes.get((chain, norm_addr(addr)), "0x")

    async def get_storage_at(self, chain, addr, slot):
        return self.storages.get((chain, norm_addr(addr), slot.lower()), "0x" + "0" * 64)

    async def call(self, chain, to, data, *, from_=None, block=None):
        return self.calls.get((chain, norm_addr(to), data.lower()), "0x")

    async def codehash(self, chain, addr) -> str | None:
        return self.codehashes.get((chain, norm_addr(addr)))

    async def get_logs(self, chain, addr, topics=None, from_block=0, to_block="latest"):
        return []

    async def get_creation(self, chain, addr):
        return None


def _run():
    return asyncio.run(reconstruct([(1, A)], FakeRpc(), probe_chains=[1, 10]))


def test_proxy_resolved_from_single_seed():
    g = _run()
    a = g.get_node(1, A)
    assert a is not None
    assert a.proxy_kind == ProxyKind.EIP1967_TRANSPARENT
    assert a.implementation == norm_addr(B)
    assert a.admin == norm_addr(ADMIN)
    assert a.is_scope is True and a.membership == "member"


def test_expansion_reaches_impl_admin_owner():
    g = _run()
    assert g.has_node(1, B)      # impl
    assert g.has_node(1, ADMIN)  # admin
    assert g.has_node(1, OWNER)  # owner
    assert g.get_node(1, OWNER).node_type == NodeType.EOA
    # impl inherits scope from the proxy
    assert g.get_node(1, B).is_scope is True


def test_edges_present():
    g = _run()
    triples = {(e.src, e.dst, e.edge_type) for e in g.edges}
    assert (node_key(1, A), node_key(1, B), EdgeType.IS_PROXY_FOR) in triples
    assert (node_key(1, ADMIN), node_key(1, A), EdgeType.HOLDS_ROLE_OVER) in triples
    assert (node_key(1, OWNER), node_key(1, A), EdgeType.HOLDS_ROLE_OVER) in triples


def test_owner_role_captured():
    g = _run()
    roles = {r.name: r.holder for r in g.get_node(1, A).roles}
    assert roles.get("owner") == norm_addr(OWNER)
    assert roles.get("proxyAdmin") == norm_addr(ADMIN)


def test_cross_chain_mirror_detected():
    g = _run()
    assert 1 in g.chains and 10 in g.chains
    triples = {(e.src, e.dst, e.edge_type) for e in g.edges}
    assert (node_key(1, A), node_key(10, A), EdgeType.MIRRORS_DEPLOYMENT) in triples
    assert g.has_node(10, A)


def test_roots_are_seed_keys():
    g = _run()
    assert g.roots == [node_key(1, A)]


def test_membership_computed_from_signals():
    g = _run()
    # impl inherits scope → member
    assert g.get_node(1, B).membership == "member"
    # ADMIN is a contract authority (has code) → member
    assert g.get_node(1, ADMIN).membership == "member"
    # OWNER is an EOA (no code) → external operator, never a member; authority lives in edges
    owner = g.get_node(1, OWNER)
    assert owner.node_type == NodeType.EOA
    assert owner.membership == "external"
    assert any("EOA" in note for note in owner.notes)
    # mirror of the same address on chain 10 → member (multichain_mirror)
    assert g.get_node(10, A).membership == "member"
