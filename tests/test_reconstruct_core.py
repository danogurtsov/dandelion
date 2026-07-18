"""
End-to-end tests for the reconstruct orchestration (the actual product), driven by a rich
FakeRpc that models a mini-lending protocol. Covers what unit tests can't: the multi-level
membership fixpoint, purpose-aware getter expansion, reserve-keyed struct discovery, token
roles, known-external handling, and block-pinning.
"""
import asyncio

from eth_utils import keccak

from dandelion.domain.models import norm_addr
from dandelion.ports import SourceInfo
from dandelion.services.reconstruct import reconstruct

# addresses (distinct, address-typed)
POOL = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20
ACL = "0x" + "33" * 20
ORACLE = "0x" + "44" * 20
USDC = "0x" + "55" * 20                              # reserve underlying (external asset)
ATOKEN = "0x" + "66" * 20                            # per-reserve own contract
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # known-external


def _sel(sig: str) -> str:
    return "0x" + keccak(text=sig).hex()[:8]


def _word(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:]


def _addr_array(addrs: list[str]) -> str:
    body = f"{32:064x}" + f"{len(addrs):064x}"
    for a in addrs:
        body += "0" * 24 + a[2:]
    return "0x" + body


def _struct_with(addrs: list[str]) -> str:
    # a struct return: a number word (not an address) then the address components
    body = "f" * 64
    for a in addrs:
        body += "0" * 24 + a[2:]
    return "0x" + body


class FakeSource:
    """Verified-source ABIs for the mini-protocol; everything else unverified."""
    ABIS = {
        norm_addr(POOL): [
            {"type": "function", "name": "ADDRESSES_PROVIDER", "stateMutability": "view",
             "inputs": [], "outputs": [{"type": "address"}]},
            {"type": "function", "name": "getReservesList", "stateMutability": "view",
             "inputs": [], "outputs": [{"type": "address[]"}]},
            {"type": "function", "name": "getReserveData", "stateMutability": "view",
             "inputs": [{"type": "address"}],
             "outputs": [{"type": "tuple", "components": [
                 {"type": "uint256"}, {"type": "address", "name": "aTokenAddress"}]}]},
        ],
        norm_addr(PROVIDER): [
            {"type": "function", "name": "getACLManager", "stateMutability": "view",
             "inputs": [], "outputs": [{"type": "address"}]},
            {"type": "function", "name": "getPriceOracle", "stateMutability": "view",
             "inputs": [], "outputs": [{"type": "address"}]},
        ],
    }
    NAMES = {norm_addr(POOL): "Pool", norm_addr(PROVIDER): "PoolAddressesProvider",
             norm_addr(ACL): "ACLManager", norm_addr(ORACLE): "AaveOracle",
             norm_addr(ATOKEN): "AToken", norm_addr(USDC): "USDC"}

    async def resolve(self, chain, addr, code=None):
        a = norm_addr(addr)
        if a in self.NAMES:
            return SourceInfo(tier="verified", name=self.NAMES[a], abi=self.ABIS.get(a, []))
        return None


class FakeRpc:
    def __init__(self):
        self.blocks_seen: set = set()
        self.pin_block = None
        self.codes = {norm_addr(a): "0x60code" for a in
                      (POOL, PROVIDER, ACL, ORACLE, USDC, ATOKEN, WETH)}
        gRD = _sel("getReserveData(address)")
        self.calls = {
            (norm_addr(POOL), _sel("ADDRESSES_PROVIDER()")): _word(PROVIDER),
            (norm_addr(POOL), _sel("getReservesList()")): _addr_array([USDC, WETH]),
            (norm_addr(POOL), gRD + "0" * 24 + USDC[2:]): _struct_with([ATOKEN]),
            (norm_addr(PROVIDER), _sel("getACLManager()")): _word(ACL),
            (norm_addr(PROVIDER), _sel("getPriceOracle()")): _word(ORACLE),
        }

    async def get_code(self, chain, addr):
        self.blocks_seen.add(self.pin_block)
        return self.codes.get(norm_addr(addr), "0x")

    async def get_storage_at(self, chain, addr, slot):
        return "0x" + "0" * 64                       # no proxy slots → not a proxy

    async def call(self, chain, to, data, *, from_=None, block=None):
        self.blocks_seen.add(block if block is not None else self.pin_block)
        # exact selector+arg match; else the plain 4-byte selector; else revert-like "0x"
        return self.calls.get((norm_addr(to), data)) or self.calls.get((norm_addr(to), data[:10])) or "0x"

    async def codehash(self, chain, addr):
        c = self.codes.get(norm_addr(addr))
        return "0xcode" + norm_addr(addr)[-4:] if c and c != "0x" else None

    async def get_logs(self, chain, addr, topics=None, from_block=0, to_block="latest"):
        return []

    async def trace_transaction(self, chain, tx):
        return []

    async def get_creation(self, chain, addr):
        return None


def _run(**kw):
    return asyncio.run(reconstruct([(1, POOL)], FakeRpc(), source=FakeSource(),
                                   probe_chains=[1], **kw))


def test_multilevel_membership_fixpoint():
    g = _run()
    # Pool(seed) -> Provider -> ACL / Oracle all become member via the struct-getter chain
    assert g.get_node(1, POOL).membership == "member"
    assert g.get_node(1, PROVIDER).membership == "member"
    assert g.get_node(1, ACL).membership == "member"      # 2 levels deep
    assert g.get_node(1, ORACLE).membership == "member"


def test_reserve_underlying_is_external():
    g = _run()
    usdc = g.get_node(1, USDC)
    assert usdc is not None and usdc.membership == "external"
    assert usdc.token_role == "reserved"


def test_reserve_keyed_component_discovered():
    g = _run()
    at = g.get_node(1, ATOKEN)                             # only reachable via getReserveData
    assert at is not None and at.membership == "member"


def test_known_external_is_filtered_out():
    # WETH is known-external infra: it is not even added as a node (no clutter), so it can
    # never leak into membership. USDC (a real project reserve) is kept and marked reserved.
    g = _run()
    assert g.get_node(1, WETH) is None
    assert g.get_node(1, USDC) is not None


def test_block_pin_is_honored():
    rpc = FakeRpc()
    asyncio.run(reconstruct([(1, POOL)], rpc, source=FakeSource(), probe_chains=[1],
                            at_block=17_000_000))
    # every read saw the pinned block (FakeRpc mirrors JsonRpcClient's pin_block behavior)
    assert rpc.pin_block == 17_000_000
    assert rpc.blocks_seen == {17_000_000}


def test_no_precision_leak_on_mini_protocol():
    from dandelion.domain.audit import membership_audit
    g = _run()
    au = membership_audit(g)
    assert au.leaked_members == 0 and au.precision_proxy == 1.0
