"""
Known read selectors and decoders — pure core (no keccak).

Lets us build calldata for common no-arg getters and decode the response without
external dependencies. For arbitrary signatures the selector is computed in the
adapter (keccak); this is a fast path for the checks we need most.
"""
from __future__ import annotations

from .models import addr_from_slot

# signature -> 4-byte selector (keccak256(sig)[:4])
KNOWN_SELECTORS: dict[str, str] = {
    "owner()": "0x8da5cb5b",
    "admin()": "0xf851a440",
    "implementation()": "0x5c60da1b",
    "paused()": "0x5c975abb",
    "getOwners()": "0xa0e67e2b",
    "getThreshold()": "0xe75235b8",
    "factory()": "0xc45a0155",
    "token0()": "0x0dfe1681",
    "token1()": "0xd21220a7",
    "asset()": "0x38d52e0f",
    "decimals()": "0x313ce567",
    "name()": "0x06fdde03",
    "symbol()": "0x95d89b41",
    "getMinDelay()": "0xf27a0c92",
    "DEFAULT_ADMIN_ROLE()": "0xa217fddf",
    "proxiableUUID()": "0x52d1902d",
}


def read_calldata(sig: str) -> str | None:
    """Calldata for a known no-arg getter, else None (the adapter computes the selector)."""
    return KNOWN_SELECTORS.get(sig)


def decode_address(word: str | None) -> str | None:
    """Decode an address from a 32-byte response."""
    return addr_from_slot(word)


def decode_address_strict(word: str | None) -> str | None:
    """
    Decode an address ONLY if the word is genuinely address-typed:
    the top 12 bytes are zero AND the high bytes of the 20-byte address are non-zero
    (otherwise it is a small uint like getMinDelay()=172800, not an address).
    """
    if not word:
        return None
    w = word[2:] if word.startswith("0x") else word
    w = w.rjust(64, "0")[-64:]
    if w[:24] != "0" * 24:          # top 12 bytes non-zero → not an address
        return None
    if w[24:32] == "0" * 8:         # high 4 bytes of the address are zero → likely a small uint
        return None
    return addr_from_slot(word)


def decode_address_array(data: str | None, *, cap: int = 60) -> list[str]:
    """Decode an ABI-encoded `address[]` from return data (offset+length+elements)."""
    if not data:
        return []
    d = data[2:] if data.startswith("0x") else data
    words = [d[i:i + 64] for i in range(0, len(d), 64)]
    if len(words) < 2:
        return []
    try:
        off = int(words[0], 16) // 32          # offset to array data (usually 1 word)
        length = int(words[off], 16)
    except (ValueError, IndexError):
        return []
    out: list[str] = []
    for i in range(off + 1, min(off + 1 + length, len(words))):
        a = addr_from_slot("0x" + words[i])
        if a:
            out.append(a)
        if len(out) >= cap:
            break
    return out


def address_words(data: str | None, *, cap: int = 12) -> list[str]:
    """
    All address-typed 32-byte words of arbitrary return data (struct/tuple).
    For `getReserveData(asset)→struct` it pulls out aToken/stableDebt/variableDebt/strategy,
    dropping numeric words (indices/rates — high bytes non-zero). Deduplicated, order preserved.
    """
    if not data:
        return []
    d = data[2:] if data.startswith("0x") else data
    out: list[str] = []
    for i in range(0, len(d) - 63, 64):
        a = decode_address_strict("0x" + d[i:i + 64])
        if a and a not in out:
            out.append(a)
            if len(out) >= cap:
                break
    return out


def decode_uint(word: str | None) -> int | None:
    if not word:
        return None
    w = word[2:] if word.startswith("0x") else word
    try:
        return int(w, 16) if w else None
    except ValueError:
        return None


def decode_bool(word: str | None) -> bool | None:
    v = decode_uint(word)
    return None if v is None else bool(v)
