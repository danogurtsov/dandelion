"""
Getter dictionary by PURPOSE (read-purpose) — pure core (no I/O).

Key idea (see also membership-closure): an address-returning getter is filtered NOT
by contract type, but by the PURPOSE of the read:
  • struct  — a component of the project architecture (provider/configurator/oracle/acl/registry/…).
              We crawl deeper AND emit a membership signal (the project cluster unfolds itself).
  • asset   — an EXTERNAL asset (reserve tokens, underlying, token0/1). Added as a leaf,
              NOT crawled deeper, membership = external (otherwise the budget leaks into foreign tokens).
  • generic — any other address getter from the ABI: follow it, but membership is only a candidate.

The same struct signatures form the set for a SPECULATIVE probe: they are called on scope
contracts even without an ABI (source unavailable) — the tool "feels out" the architecture via reads.
"""
from __future__ import annotations

# --- structural single-address getters (project components) ---
STRUCT_GETTERS: frozenset[str] = frozenset({
    # registry / addresses-provider
    "ADDRESSES_PROVIDER()", "getAddressesProvider()", "addressesProvider()",
    "getAddressesProviderRegistry()", "getPoolAddressesProviderRegistry()",
    # pool / core
    "POOL()", "getPool()", "pool()", "core()", "getCore()",
    "getPoolConfigurator()", "poolConfigurator()",
    "getPoolDataProvider()", "dataProvider()", "protocolDataProvider()",
    # oracle
    "getPriceOracle()", "priceOracle()", "oracle()", "getOracle()",
    "getPriceOracleSentinel()", "getFallbackOracle()", "sequencerOracle()",
    # access control / governance
    "getACLManager()", "aclManager()", "getACLAdmin()", "acl()",
    "governance()", "getGovernance()", "governor()", "guardian()", "getGuardian()",
    "timelock()", "getTimelock()", "emergencyAdmin()", "riskAdmin()",
    "roleRegistry()", "getRoleRegistry()", "authority()", "accessControl()",
    # incentives / rewards
    "getRewardsController()", "rewardsController()", "incentivesController()",
    "getIncentivesController()", "INCENTIVES_CONTROLLER()", "emissionManager()",
    # strategy / rates / managers
    "getInterestRateStrategy()", "interestRateStrategy()", "getReserveInterestRateStrategy()",
    "strategy()", "getStrategy()", "manager()", "getManager()", "controller()",
    "comptroller()", "getComptroller()",
    # treasury / fees
    "treasury()", "getTreasury()", "collector()", "feeRecipient()", "feeCollector()",
    "feeDistributor()", "protocolFeeRecipient()",
    # factory / registry
    "factory()", "getFactory()", "registry()", "getRegistry()", "vaultFactory()",
    # vault / router / messaging
    "vault()", "getVault()", "VAULT()", "router()", "getRouter()", "swapRouter()",
    "gauge()", "voter()", "votingEscrow()", "minter()", "escrow()", "delegate()",
    "endpoint()", "lzEndpoint()", "messenger()", "gateway()", "getBridge()",
    "WRAPPED_TOKEN_GATEWAY()", "wrappedTokenGateway()",
})

# --- asset getters: EXTERNAL token/asset (leaf, not crawled, external) ---
ASSET_GETTERS: frozenset[str] = frozenset({
    "underlying()", "UNDERLYING_ASSET_ADDRESS()", "asset()", "getAsset()",
    "token()", "getToken()", "token0()", "token1()",
    "stakingToken()", "rewardToken()", "reserveToken()", "collateralToken()",
    "debtToken()", "borrowToken()", "aToken()", "stableDebtToken()",
    "variableDebtToken()", "want()", "depositToken()", "wantToken()",
    "WETH()", "weth()", "WNATIVE()", "wrappedNative()", "WETH9()", "stablecoin()",
})

# --- asset enumeration (address[]): reserve lists → external leaves ---
ASSET_ARRAY_GETTERS: frozenset[str] = frozenset({
    "getReservesList()", "getAllReservesTokens()", "reservesList()",
    "getTokens()", "getRewardsList()", "underlyingAssets()",
})


def getter_purpose(sig: str) -> str:
    """Purpose of an address getter: 'struct' | 'asset' | 'generic'."""
    s = (sig or "").strip()
    if s in STRUCT_GETTERS:
        return "struct"
    if s in ASSET_GETTERS or s in ASSET_ARRAY_GETTERS:
        return "asset"
    return "generic"


# priority order for the blind probe: high-value registry/provider getters first
# (they reveal the whole cluster), then the remaining structural ones. Deterministic.
_SPEC_PRIORITY: tuple[str, ...] = (
    "ADDRESSES_PROVIDER()", "getAddressesProvider()", "addressesProvider()",
    "POOL()", "getPool()", "getPoolConfigurator()", "getPriceOracle()",
    "getACLManager()", "getPoolDataProvider()", "getRewardsController()",
    "getAddressesProviderRegistry()", "registry()", "factory()", "getFactory()",
    "controller()", "comptroller()", "oracle()", "priceOracle()",
    "governance()", "governor()", "timelock()", "guardian()", "treasury()",
    "vault()", "getVault()", "router()", "strategy()", "manager()",
    "incentivesController()", "INCENTIVES_CONTROLLER()", "authority()", "roleRegistry()",
)


def speculative_struct_getters() -> list[str]:
    """Structural signatures for the blind probe (no ABI): priority ones + the rest, deterministic."""
    rest = sorted(STRUCT_GETTERS - set(_SPEC_PRIORITY))
    return [s for s in _SPEC_PRIORITY if s in STRUCT_GETTERS] + rest
