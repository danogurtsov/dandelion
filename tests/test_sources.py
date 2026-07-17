"""Source-resolver unit tests: parsers + ladder ordering (no network)."""
import asyncio

from dandelion.adapters.sources.blockscout import parse_blockscout
from dandelion.adapters.sources.etherscan_v2 import parse_etherscan
from dandelion.adapters.sources.ladder import SourceLadder
from dandelion.adapters.sources.sourcify import parse_sourcify


def test_parse_sourcify():
    data = {
        "match": "exact_match",
        "metadata": {
            "settings": {"compilationTarget": {"src/Morpho.sol": "Morpho"}},
            "output": {"abi": [{"type": "function", "name": "owner"}]},
        },
    }
    info = parse_sourcify(data)
    assert info.name == "Morpho" and info.tier == "verified" and info.abi


def test_parse_sourcify_empty():
    assert parse_sourcify({"metadata": {}}) is None


def test_parse_etherscan():
    res = {"ContractName": "Vault", "ABI": '[{"type":"function","name":"asset"}]'}
    info = parse_etherscan(res)
    assert info.name == "Vault" and info.abi and info.tier == "verified"


def test_parse_etherscan_unverified():
    res = {"ContractName": "", "ABI": "Contract source code not verified"}
    assert parse_etherscan(res) is None


def test_parse_blockscout():
    info = parse_blockscout({"is_verified": True, "name": "Pool", "abi": [{"type": "function"}]})
    assert info.name == "Pool" and info.tier == "verified"


def test_parse_blockscout_unverified():
    assert parse_blockscout({"is_verified": False, "name": None}) is None


class _R:
    """Fake resolver: returns the given info (or None)."""
    def __init__(self, info):
        self.info = info

    async def resolve(self, chain, addr, code=None):
        return self.info


def test_ladder_returns_first_hit():
    from dandelion.ports import SourceInfo
    ladder = SourceLadder(resolvers=[_R(None), _R(SourceInfo(tier="verified", name="Found")), _R(None)])
    info = asyncio.run(ladder.resolve(1, "0x" + "a" * 40, code="0x60"))
    assert info.name == "Found"


def test_ladder_all_miss():
    ladder = SourceLadder(resolvers=[_R(None), _R(None)])
    assert asyncio.run(ladder.resolve(1, "0x" + "a" * 40)) is None


def test_default_ladder_etherscan_toggle(monkeypatch):
    from dandelion.adapters.sources.etherscan_v2 import EtherscanV2Resolver
    from dandelion.adapters.sources.ladder import default_ladder

    def has_etherscan(ladder):
        return any(isinstance(r, EtherscanV2Resolver) for r in ladder.resolvers)

    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    # auto without a key → no Etherscan
    assert not has_etherscan(default_ladder())
    # auto with a key (env) → present
    monkeypatch.setenv("ETHERSCAN_API_KEY", "KEY")
    assert has_etherscan(default_ladder())
    # force-off even with a key → absent (keyless mode)
    assert not has_etherscan(default_ladder(use_etherscan=False))
    # force-on with a key argument → present even without env
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    assert has_etherscan(default_ladder(use_etherscan=True, etherscan_key="K2"))


def test_selector_of():
    from dandelion.services.probes import selector_of
    assert selector_of("owner()") == "0x8da5cb5b"          # known
    assert selector_of("getMinDelay()") == "0xf27a0c92"    # known
    s = selector_of("someRandomGetter()")                  # keccak-computed
    assert s and s.startswith("0x") and len(s) == 10
    assert selector_of("transfer(address,uint256)") is None  # args not supported


def test_decode_address_strict():
    from dandelion.domain.reads import decode_address_strict
    addr = "0x000000000000000000000000" + "ab" * 20        # address-typed
    assert decode_address_strict(addr) == "0x" + "ab" * 20
    small = "0x" + "0" * 59 + "2a300"                        # uint 172800 → not an address
    assert decode_address_strict(small) is None
    assert decode_address_strict("0x" + "0" * 64) is None    # zero
