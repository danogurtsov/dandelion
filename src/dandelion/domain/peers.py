"""
Cross-chain peer-config parsing — pure core (no I/O).

A project lives on many chains with DIFFERENT code and at DIFFERENT addresses (not a
mirror): a LayerZero OApp/OFT knows its remote "peers" via `peers(uint32 eid) → bytes32`
(V2) or `trustedRemoteLookup(uint16) → bytes` (V1). We extract the remote
(chain_id, address) so we can link deployments with `PEER_OF` edges even when the
addresses differ.
"""
from __future__ import annotations

from .models import addr_from_slot

# LayerZero V2 Endpoint ID → chain_id (only chains in our registry; unknown ones are skipped)
LZ_V2_EID_TO_CHAIN: dict[int, int] = {
    30101: 1,       # ethereum
    30102: 56,      # bsc
    30106: 43114,   # avalanche
    30109: 137,     # polygon
    30110: 42161,   # arbitrum
    30111: 10,      # optimism
    30145: 100,     # gnosis
    30183: 59144,   # linea
    30184: 8453,    # base
    30214: 534352,  # scroll
}

# LayerZero V1 chainId → chain_id
LZ_V1_CHAINID_TO_CHAIN: dict[int, int] = {
    101: 1,
    102: 56,
    106: 43114,
    109: 137,
    110: 42161,
    111: 10,
    145: 100,
    183: 59144,
    184: 8453,
    214: 534352,
}


def known_lz_v2_eids() -> list[int]:
    """EIDs to iterate over peers(eid) (LZ has no on-chain enumeration)."""
    return list(LZ_V2_EID_TO_CHAIN)


def known_lz_v1_chainids() -> list[int]:
    return list(LZ_V1_CHAINID_TO_CHAIN)


def eid_to_chain(eid: int) -> int | None:
    return LZ_V2_EID_TO_CHAIN.get(eid)


def v1_chainid_to_chain(cid: int) -> int | None:
    return LZ_V1_CHAINID_TO_CHAIN.get(cid)


def decode_peer_bytes32(word: str | None) -> str | None:
    """peers(eid) → bytes32 (address in the low 20 bytes, left-padded). None if zero."""
    return addr_from_slot(word)


def decode_trusted_remote(data: str | None) -> str | None:
    """
    trustedRemoteLookup(uint16) → bytes = abi.encodePacked(remoteAddr, localAddr).
    ABI return: [offset][length][packed…]; the remote address = FIRST 20 bytes of the packed data.
    """
    if not data:
        return None
    d = data[2:] if data.startswith("0x") else data
    if len(d) < 64 * 3:   # offset + length + at least one data word
        return None
    try:
        length = int(d[64:128], 16)
    except ValueError:
        return None
    if length < 20:
        return None
    payload = d[128:128 + length * 2]
    remote = payload[:40]
    if not remote or set(remote) == {"0"}:
        return None
    return addr_from_slot("0x" + remote.rjust(64, "0"))
