"""
Probe helpers — high-level checks on top of RpcPort.

These are the "probes" the exploring LLM requests: read an owner/role/value, or
call as contract X (an access-control check).
"""
from __future__ import annotations

import asyncio

from ..domain.models import addr_from_slot, is_zero, norm_addr
from ..domain.reads import (
    decode_address,
    decode_address_strict,
    decode_bool,
    decode_uint,
    read_calldata,
)
from ..ports import RpcPort


async def read_addr(rpc: RpcPort, chain: int, to: str, sig: str) -> str | None:
    """Read an address getter (owner()/factory()/asset()...). None if absent/revert."""
    data = read_calldata(sig)
    if not data:
        return None
    try:
        word = await rpc.call(chain, to, data)
    except Exception:
        return None
    a = decode_address(word)
    return None if (a is None or is_zero(a)) else a


async def read_uint(rpc: RpcPort, chain: int, to: str, sig: str) -> int | None:
    data = read_calldata(sig)
    if not data:
        return None
    try:
        return decode_uint(await rpc.call(chain, to, data))
    except Exception:
        return None


async def read_bool(rpc: RpcPort, chain: int, to: str, sig: str) -> bool | None:
    data = read_calldata(sig)
    if not data:
        return None
    try:
        return decode_bool(await rpc.call(chain, to, data))
    except Exception:
        return None


def selector_of(sig: str) -> str | None:
    """4-byte selector for a no-arg signature: known or keccak. Args not supported."""
    known = read_calldata(sig)
    if known:
        return known
    if not sig.endswith("()"):
        return None  # we don't encode signatures with arguments
    try:
        from eth_utils import keccak  # type: ignore
        return "0x" + keccak(text=sig).hex()[:8]
    except Exception:  # noqa: BLE001
        return None


async def read_raw(rpc: RpcPort, chain: int, to: str, sig: str) -> str | None:
    """Call an arbitrary no-arg getter, return the raw 32-byte word (or None)."""
    data = selector_of(sig)
    if not data:
        return None
    try:
        word = await rpc.call(chain, to, data)
        return word if word and word != "0x" else None
    except Exception:  # noqa: BLE001
        return None


# keccak256("RoleGranted(bytes32,address,address)")
ROLE_GRANTED_TOPIC = "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d"
ROLE_REVOKED_TOPIC = "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b"
DEFAULT_ADMIN_ROLE = "0x" + "00" * 32

# keccak256(role-name) → human-readable name (Aave role hub and standard OZ roles)
KNOWN_ROLES: dict[str, str] = {
    DEFAULT_ADMIN_ROLE: "DEFAULT_ADMIN_ROLE",
    "0x12ad05bde78c5ab75238ce885307f96ecd482bb402ef831f99e7018a0f169b7b": "POOL_ADMIN",
    "0x5c91514091af31f62f596a314af7d5be40146b2f2355969392f055e12e0982fb": "EMERGENCY_ADMIN",
    "0x8aa855a911518ecfbe5bc3088c8f3dda7badf130faaf8ace33fdc33828e18167": "RISK_ADMIN",
    "0x19c860a63258efbd0ecb7d55c626237bf5c2044c26c073390b74f0c13c857433": "ASSET_LISTING_ADMIN",
    "0x08fb31c3e81624356c3314088aa971b73bcc82d22bc3e3b184b4593077ae3278": "BRIDGE",
    "0x939b8dfb57ecef2aea54a93a15e86768b9d4089f1ba61c245e6ec980695f4ca4": "FLASH_BORROWER",
}


def role_name(role_hex: str) -> str:
    """Role name from its keccak hash (known Aave/OZ roles), else a shortened hash."""
    r = (role_hex or "").lower()
    return KNOWN_ROLES.get(r, f"role:{r[:10]}")


# admin roles = project AUTHORITY (governance). Operational ones (FLASH_BORROWER/BRIDGE) are
# external integrators/whitelist, NOT authorities: their holders must not confer membership.
ADMIN_ROLES: frozenset[str] = frozenset({
    DEFAULT_ADMIN_ROLE,
    "0x12ad05bde78c5ab75238ce885307f96ecd482bb402ef831f99e7018a0f169b7b",  # POOL_ADMIN
    "0x5c91514091af31f62f596a314af7d5be40146b2f2355969392f055e12e0982fb",  # EMERGENCY_ADMIN
    "0x8aa855a911518ecfbe5bc3088c8f3dda7badf130faaf8ace33fdc33828e18167",  # RISK_ADMIN
    "0x19c860a63258efbd0ecb7d55c626237bf5c2044c26c073390b74f0c13c857433",  # ASSET_LISTING_ADMIN
})


def is_admin_role(role_hex: str) -> bool:
    """True for governance/admin roles (project authority), False for operational ones."""
    return (role_hex or "").lower() in ADMIN_ROLES


async def default_admins(rpc: RpcPort, chain: int, addr: str, *, limit: int = 8) -> list[str]:
    """
    Holders of the contract's DEFAULT_ADMIN_ROLE (AccessControl/ACLManager) from RoleGranted logs.
    Reads role-based authority where there's no owner()/admin slot (Aave governance, etc.).
    """
    try:
        logs = await rpc.get_logs(chain, addr, topics=[ROLE_GRANTED_TOPIC, DEFAULT_ADMIN_ROLE],
                                  from_block=0)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for lg in logs:
        tp = lg.get("topics") or []
        if len(tp) >= 3:
            a = addr_from_slot(tp[2])   # topic2 = account (indexed)
            if a and a not in out:
                out.append(a)
        if len(out) >= limit:
            break
    return out


async def role_holders(rpc: RpcPort, chain: int, addr: str, *, limit: int = 24) -> list[tuple[str, str]]:
    """
    Holders of ALL roles of a role hub (ACLManager/RoleRegistry) — not just DEFAULT_ADMIN.
    Accounts for RoleRevoked (revoked roles aren't counted as authority). Returns [(role_hex, holder)].
    This is how Aave's project authorities (POOL_ADMIN/EMERGENCY_ADMIN/…) get folded into membership.
    """
    try:
        granted = await rpc.get_logs(chain, addr, topics=[ROLE_GRANTED_TOPIC], from_block=0)
        revoked = await rpc.get_logs(chain, addr, topics=[ROLE_REVOKED_TOPIC], from_block=0)
    except Exception:  # noqa: BLE001
        return []

    def _pairs(logs: list[dict]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for lg in logs:
            tp = lg.get("topics") or []
            if len(tp) >= 3:
                role = (tp[1] or "").lower()
                acct = addr_from_slot(tp[2])
                if role and acct:
                    out.append((role, acct))
        return out

    revoked_set = set(_pairs(revoked))
    active: list[tuple[str, str]] = []
    for pair in _pairs(granted):
        if pair not in revoked_set and pair not in active:
            active.append(pair)
        if len(active) >= limit:
            break
    return active


def _keccak_selector(sig: str) -> str | None:
    try:
        from eth_utils import keccak  # type: ignore
        return "0x" + keccak(text=sig).hex()[:8]
    except Exception:  # noqa: BLE001
        return None


async def read_addr_at_index(rpc: RpcPort, chain: int, to: str, name: str, i: int) -> str | None:
    """Call `name(uint256)` with index i, return the address (or None on revert/zero)."""
    sel = _keccak_selector(f"{name}(uint256)")
    if not sel:
        return None
    data = sel + f"{i:064x}"
    try:
        word = await rpc.call(chain, to, data)
    except Exception:  # noqa: BLE001
        return None
    a = decode_address_strict(word)
    return a if (a and not is_zero(a)) else None


async def reserve_components(
    rpc: RpcPort, chain: int, to: str, name: str, reserves: list[str],
    *, cap_reserves: int = 60,
) -> list[str]:
    """
    Call `name(address)` (Aave getReserveData/Compound markets) over a list of reserves,
    pull address components from the struct return (aToken/debt/strategy). Batched-parallel, dedup.
    """
    from ..domain.reads import address_words

    sel = _keccak_selector(f"{name}(address)")
    if not sel:
        return []
    targets = reserves[:cap_reserves]

    async def _one(res: str) -> list[str]:
        a = norm_addr(res)
        if not a:
            return []
        try:
            raw = await rpc.call(chain, to, sel + a[2:].rjust(64, "0"))
        except Exception:  # noqa: BLE001
            return []
        return address_words(raw)

    out: list[str] = []
    for batch_res in await asyncio.gather(*[_one(r) for r in targets]):
        for a in batch_res:
            if a not in out:
                out.append(a)
    return out


async def enumerate_address_index(
    rpc: RpcPort, chain: int, to: str, name: str, *, cap: int = 40, batch: int = 10,
) -> list[str]:
    """
    Enumerate `name(0), name(1), …` (batched-parallel, cap). Stop when an ENTIRE batch is
    empty (tolerant of 1-based indexing like Fluid `getVaultAddress` and single gaps).
    """
    out: list[str] = []
    for start in range(0, cap, batch):
        res = await asyncio.gather(
            *[read_addr_at_index(rpc, chain, to, name, i) for i in range(start, start + batch)]
        )
        non_null = [a for a in res if a]
        out.extend(non_null)
        if not non_null:          # whole batch empty → end of list
            break
    return out[:cap]


async def call_as(rpc: RpcPort, chain: int, from_: str, to: str, data: str) -> str | None:
    """Call `to` as `from_` (override msg.sender) — an access-control check.
    Returns the return-data or None on revert."""
    try:
        return await rpc.call(chain, to, data, from_=from_)
    except Exception:
        return None


# LayerZero selectors (precomputed)
SEL_PEERS = "0xbb0b6a53"              # peers(uint32)
SEL_TRUSTED_REMOTE = "0x7533d788"     # trustedRemoteLookup(uint16)
SEL_ENDPOINT = "0x5e280f11"           # endpoint()
SEL_LZ_ENDPOINT = "0xb353aaa7"        # lzEndpoint()


async def is_lz_oapp(rpc: RpcPort, chain: int, addr: str) -> bool:
    """LayerZero OApp/endpoint? (endpoint()/lzEndpoint() return a non-zero address)."""
    for sel in (SEL_ENDPOINT, SEL_LZ_ENDPOINT):
        try:
            w = await rpc.call(chain, addr, sel)
        except Exception:  # noqa: BLE001
            continue
        if decode_address_strict(w):
            return True
    return False


async def enumerate_lz_peers(
    rpc: RpcPort, chain: int, addr: str, *, cap: int = 16,
) -> list[tuple[int, str]]:
    """
    Cross-chain peers of a LayerZero contract → [(remote_chain_id, remote_addr)].
    V2: iterate peers(eid) over known EIDs; V1 fallback: trustedRemoteLookup(chainId).
    No on-chain enumeration → we iterate a curated list of chains. None-safe.
    """
    from ..domain.peers import (
        decode_peer_bytes32,
        decode_trusted_remote,
        eid_to_chain,
        known_lz_v1_chainids,
        known_lz_v2_eids,
        v1_chainid_to_chain,
    )

    out: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    # --- V2: peers(uint32 eid) ---
    eids = known_lz_v2_eids()
    v2 = await asyncio.gather(*[
        _call_quiet(rpc, chain, addr, SEL_PEERS + f"{eid:064x}") for eid in eids
    ])
    for eid, word in zip(eids, v2, strict=False):
        remote = decode_peer_bytes32(word)
        rc = eid_to_chain(eid)
        if remote and rc and rc != chain and (rc, remote) not in seen:
            seen.add((rc, remote))
            out.append((rc, remote))

    # --- V1 fallback (only if V2 returned nothing): trustedRemoteLookup(uint16) ---
    if not out:
        cids = known_lz_v1_chainids()
        v1 = await asyncio.gather(*[
            _call_quiet(rpc, chain, addr, SEL_TRUSTED_REMOTE + f"{cid:064x}") for cid in cids
        ])
        for cid, data in zip(cids, v1, strict=False):
            remote = decode_trusted_remote(data)
            rc = v1_chainid_to_chain(cid)
            if remote and rc and rc != chain and (rc, remote) not in seen:
                seen.add((rc, remote))
                out.append((rc, remote))

    return out[:cap]


async def _call_quiet(rpc: RpcPort, chain: int, to: str, data: str) -> str | None:
    try:
        return await rpc.call(chain, to, data)
    except Exception:  # noqa: BLE001
        return None
