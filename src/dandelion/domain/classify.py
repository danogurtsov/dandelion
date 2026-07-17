"""
Contract-type classification from bytecode selectors — pure core (no calls).

The EVM dispatcher embeds the 4-byte selectors of external functions right in the bytecode.
Presence of characteristic selectors → contract type. Cheap, deterministic, no RPC.
"""
from __future__ import annotations

from .models import NodeType

# name -> 4-byte selector (keccak256(sig)[:4])
SELECTORS: dict[str, str] = {
    # ERC20
    "transfer": "a9059cbb", "balanceOf": "70a08231", "totalSupply": "18160ddd",
    "decimals": "313ce567", "symbol": "95d89b41", "approve": "095ea7b3",
    # Gnosis Safe (multisig)
    "getOwners": "a0e67e2b", "getThreshold": "e75235b8", "execTransaction": "6a761202",
    # Timelock (OZ TimelockController)
    "getMinDelay": "f27a0c92", "schedule": "01d5062a", "executeBatch": "e38335e5",
    # AccessControl
    "hasRole": "91d14854", "getRoleAdmin": "248a9ca3",
    # Governor
    "castVote": "56781388", "propose": "da95691a", "quorum": "f8ce560a",
    # Chainlink oracle
    "latestRoundData": "feaf968c", "latestAnswer": "50d25bcd",
    # AMM factory / pool
    "createPair": "c9c65396", "allPairs": "1e3dd18b", "getPool": "1698ee82",
    "getReserves": "0902f1ac", "token0": "0dfe1681", "token1": "d21220a7",
    # ERC4626 vault
    "asset": "38d52e0f", "totalAssets": "01e1d114", "redeem": "ba087652",
    # ProxyAdmin (OZ)
    "getProxyImplementation": "204e1c7a", "upgradeAndCall": "9623609d",
}


# refine the type by contract name (when selectors did not match) — specific before generic
_NAME_HINTS: list[tuple[str, NodeType]] = [
    ("timelock", NodeType.TIMELOCK),
    ("gnosissafe", NodeType.MULTISIG),
    ("safeproxy", NodeType.MULTISIG),
    ("multisig", NodeType.MULTISIG),
    ("aggregator", NodeType.ORACLE),
    ("oracle", NodeType.ORACLE),
    ("pricefeed", NodeType.ORACLE),
    ("factory", NodeType.FACTORY),
    ("governor", NodeType.GOVERNANCE),
    ("governance", NodeType.GOVERNANCE),
    ("router", NodeType.ROUTER),
    ("vault", NodeType.VAULT),
]


def type_from_name(name: str | None) -> NodeType | None:
    """Refine the type by contract name (for nodes where selectors yielded UNKNOWN)."""
    if not name:
        return None
    n = name.lower()
    for kw, t in _NAME_HINTS:
        if kw in n:
            return t
    return None


def _tags(code_hex: str) -> set[str]:
    code = (code_hex or "").lower()
    if code.startswith("0x"):
        code = code[2:]
    return {name for name, sel in SELECTORS.items() if sel in code}


def classify_bytecode(code_hex: str) -> tuple[NodeType, list[str]]:
    """Return (node type, list of detected interface tags) from bytecode."""
    t = _tags(code_hex)
    if not code_hex or code_hex == "0x":
        return NodeType.EOA, []

    # from specific to generic
    if {"getOwners", "getThreshold", "execTransaction"} & t == {"getOwners", "getThreshold", "execTransaction"}:
        kind = NodeType.MULTISIG
    elif "getMinDelay" in t and "schedule" in t:
        kind = NodeType.TIMELOCK
    elif "castVote" in t and ("propose" in t or "quorum" in t):
        kind = NodeType.GOVERNANCE
    elif "latestRoundData" in t or "latestAnswer" in t:
        kind = NodeType.ORACLE
    elif "createPair" in t or "allPairs" in t or "getPool" in t:
        kind = NodeType.FACTORY
    elif {"getReserves", "token0", "token1"} <= t:
        kind = NodeType.POOL
    elif "asset" in t and "totalAssets" in t:
        kind = NodeType.VAULT
    elif {"transfer", "balanceOf", "totalSupply"} <= t:
        kind = NodeType.TOKEN
    else:
        kind = NodeType.UNKNOWN

    tags = sorted(t)
    if "getProxyImplementation" in t and "upgradeAndCall" in t:
        tags.append("proxy_admin")
    if {"hasRole", "getRoleAdmin"} <= t:
        tags.append("access_control")
    return kind, tags
