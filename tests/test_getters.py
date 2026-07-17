"""Tests for the getter dictionary by purpose (struct/asset/generic)."""
from dandelion.domain.getters import (
    ASSET_ARRAY_GETTERS,
    ASSET_GETTERS,
    STRUCT_GETTERS,
    getter_purpose,
    speculative_struct_getters,
)


def test_struct_getters_classified():
    for sig in ("ADDRESSES_PROVIDER()", "getACLManager()", "getPriceOracle()",
                "getPoolConfigurator()", "getRewardsController()", "factory()"):
        assert getter_purpose(sig) == "struct", sig


def test_asset_getters_classified():
    for sig in ("underlying()", "asset()", "token0()", "stakingToken()",
                "getReservesList()", "getAllReservesTokens()"):
        assert getter_purpose(sig) == "asset", sig


def test_generic_fallback():
    assert getter_purpose("someRandomThing()") == "generic"
    assert getter_purpose("") == "generic"


def test_no_overlap_struct_asset():
    assert not (STRUCT_GETTERS & ASSET_GETTERS)
    assert not (STRUCT_GETTERS & ASSET_ARRAY_GETTERS)


def test_speculative_set_is_struct_and_stable():
    spec = speculative_struct_getters()
    assert spec == speculative_struct_getters()   # deterministic (identical across calls)
    assert set(spec) == set(STRUCT_GETTERS)        # covers the entire struct set
    assert all(getter_purpose(s) == "struct" for s in spec)
    # priority: registry/provider come first
    assert spec[0] == "ADDRESSES_PROVIDER()"


def test_address_keyed_struct_getters():
    from dandelion.domain.abi import address_keyed_struct_getters
    abi = [
        {"type": "function", "name": "getReserveData", "stateMutability": "view",
         "inputs": [{"type": "address"}],
         "outputs": [{"type": "tuple", "components": [
             {"type": "uint256"}, {"type": "uint128"},
             {"type": "address", "name": "aTokenAddress"},
             {"type": "address", "name": "variableDebtTokenAddress"},
         ]}]},
        {"type": "function", "name": "getReserveNormalizedIncome", "stateMutability": "view",
         "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]},  # no addresses → skipped
        {"type": "function", "name": "getPool", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},  # no-arg → not address-keyed
    ]
    assert address_keyed_struct_getters(abi) == ["getReserveData"]


def test_address_words_extracts_struct_addresses():
    from dandelion.domain.reads import address_words
    aT = "aa" * 20
    vd = "bb" * 20
    # struct-return: config(uint), index(big uint = not an address), aToken, variableDebt
    data = ("0x"
            + "1" * 64                       # configuration — large number, not an address
            + "f" * 64                       # index — not an address (upper bytes are non-zero)
            + "0" * 24 + aT                  # aToken
            + "0" * 24 + vd)                 # variableDebt
    got = address_words(data)
    assert got == ["0x" + aT, "0x" + vd]
