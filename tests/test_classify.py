"""Unit tests for classification by bytecode selectors (no network)."""
from dandelion.domain.classify import SELECTORS, classify_bytecode
from dandelion.domain.models import NodeType


def code_with(*names: str) -> str:
    """Synthetic bytecode containing the selectors of the given functions."""
    return "0x6080" + "".join(SELECTORS[n] for n in names) + "00"


def test_token():
    kind, _ = classify_bytecode(code_with("transfer", "balanceOf", "totalSupply", "decimals"))
    assert kind == NodeType.TOKEN


def test_multisig():
    kind, _ = classify_bytecode(code_with("getOwners", "getThreshold", "execTransaction"))
    assert kind == NodeType.MULTISIG


def test_timelock():
    kind, _ = classify_bytecode(code_with("getMinDelay", "schedule"))
    assert kind == NodeType.TIMELOCK


def test_oracle():
    kind, _ = classify_bytecode(code_with("latestRoundData"))
    assert kind == NodeType.ORACLE


def test_factory():
    kind, _ = classify_bytecode(code_with("createPair", "allPairs"))
    assert kind == NodeType.FACTORY


def test_pool_beats_token():
    # the pair has both ERC20 and pool selectors — POOL should win
    kind, _ = classify_bytecode(code_with("getReserves", "token0", "token1", "transfer", "balanceOf"))
    assert kind == NodeType.POOL


def test_vault():
    kind, _ = classify_bytecode(code_with("asset", "totalAssets", "transfer", "balanceOf"))
    assert kind == NodeType.VAULT


def test_eoa_empty():
    kind, tags = classify_bytecode("0x")
    assert kind == NodeType.EOA and tags == []


def test_access_control_tag():
    _, tags = classify_bytecode(code_with("hasRole", "getRoleAdmin", "transfer", "balanceOf", "totalSupply"))
    assert "access_control" in tags


def test_type_from_name():
    from dandelion.domain.classify import type_from_name
    assert type_from_name("InstaTimelock") == NodeType.TIMELOCK
    assert type_from_name("GnosisSafeProxy") == NodeType.MULTISIG
    assert type_from_name("PoolFactory") == NodeType.FACTORY
    assert type_from_name("ChainlinkAggregator") == NodeType.ORACLE
    assert type_from_name("FluidLiquidityDummyImpl") is None
    assert type_from_name(None) is None
