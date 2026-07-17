"""
ABI analysis — pure core (no I/O).

Extract no-arg view getters that return an address. A contract exposes its own
components (`getPool()`, `getACLManager()`, `ADDRESSES_PROVIDER()`) — walking these
getters deterministically reveals the registry cluster (Aave, etc.), no LLM.
"""
from __future__ import annotations


def address_getters(abi: list | None) -> list[str]:
    """
    Signatures of no-input view/pure functions that return a single `address`.
    Returns ["getPool()", "ADDRESSES_PROVIDER()", ...] in ABI order.
    """
    out: list[str] = []
    for item in abi or []:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        if item.get("stateMutability") not in ("view", "pure"):
            continue
        if item.get("inputs"):
            continue  # no-arg only
        outs = item.get("outputs") or []
        if len(outs) == 1 and outs[0].get("type") == "address":
            name = item.get("name")
            if name:
                out.append(f"{name}()")
    return out


def indexed_address_getters(abi: list | None) -> list[str]:
    """
    Names of view functions `name(uint) -> address` (getToken/getTroveManager/allPairs) —
    a registry exposes components by index. Enumerate i=0,1,… until a gap.
    """
    out: list[str] = []
    for item in abi or []:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        if item.get("stateMutability") not in ("view", "pure"):
            continue
        ins = item.get("inputs") or []
        outs = item.get("outputs") or []
        if (len(ins) == 1 and str(ins[0].get("type", "")).startswith("uint")
                and len(outs) == 1 and outs[0].get("type") == "address"):
            name = item.get("name")
            if name:
                out.append(name)
    return out


def _outputs_have_address(outs: list | None) -> bool:
    """Whether an address appears among the outputs (including inside tuple/struct, recursively)."""
    for o in outs or []:
        t = str(o.get("type", ""))
        if t == "address" or t == "address[]":
            return True
        if t.startswith("tuple") and _outputs_have_address(o.get("components")):
            return True
    return False


def address_keyed_struct_getters(abi: list | None) -> list[str]:
    """
    Names of view functions `name(address) -> (…struct with addresses…)` — per-reserve/market data.
    Aave `getReserveData(asset)` → aToken/stableDebt/variableDebt/interestRateStrategy;
    Compound `markets(addr)`, Euler, etc. Called over the reserve list → project components.
    """
    out: list[str] = []
    for item in abi or []:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        if item.get("stateMutability") not in ("view", "pure"):
            continue
        ins = item.get("inputs") or []
        if len(ins) == 1 and ins[0].get("type") == "address" and _outputs_have_address(item.get("outputs")):
            name = item.get("name")
            if name:
                out.append(name)
    return out


def address_array_getters(abi: list | None) -> list[str]:
    """No-input view functions that return `address[]` (getReservesList/facets/…)."""
    out: list[str] = []
    for item in abi or []:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        if item.get("stateMutability") not in ("view", "pure") or item.get("inputs"):
            continue
        outs = item.get("outputs") or []
        if len(outs) == 1 and outs[0].get("type") == "address[]":
            name = item.get("name")
            if name:
                out.append(f"{name}()")
    return out
