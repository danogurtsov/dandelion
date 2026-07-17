"""
Proxy-standard detection — pure core (no I/O).

Determines the proxy type and the implementation/admin address from storage-slot
values and bytecode. The slot reader is injected (`read_slot`), so the module is
testable without a network.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .models import ProxyKind, addr_from_slot

# --------------------------------------------------------------------------- #
# Well-known slot constants (EIP-1967 / EIP-1822)
# --------------------------------------------------------------------------- #
# keccak256("eip1967.proxy.implementation") - 1
SLOT_1967_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
# keccak256("eip1967.proxy.admin") - 1
SLOT_1967_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
# keccak256("eip1967.proxy.beacon") - 1
SLOT_1967_BEACON = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
# keccak256("PROXIABLE")  (EIP-1822 UUPS legacy)
SLOT_1822 = "0xc5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7"
# keccak256("org.zeppelinos.proxy.implementation")  (pre-1967 OZ/zeppelinos — USDC FiatTokenProxy, etc.)
SLOT_ZOS = "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3"
# EIP-2535 Diamond storage marker function selector: facets()/facetAddresses()
DIAMOND_SELECTORS = ("cdffacc6", "52ef6b2c", "adfca15e", "7a0ed627")  # diamondCut/loupe

# EIP-1167 minimal proxy: 363d3d373d3d3d363d73 <impl(20)> 5af43d82803e903d91602b57fd5bf3
_MINIMAL_RE = re.compile(
    r"363d3d373d3d3d363d73([0-9a-fA-F]{40})5af43d82803e903d91602b57fd5bf3"
)
# Common variant (push0-based / vyper-style) — impl still 40 hex after 73
_MINIMAL_RE_LOOSE = re.compile(r"3d3d3d3d363d3d3773([0-9a-fA-F]{40})5af43d")

SlotReader = Callable[[str], str | None]  # slot_hex -> 32-byte word (hex) | None


@dataclass
class ProxyResult:
    kind: ProxyKind
    implementation: str | None = None
    admin: str | None = None
    beacon: str | None = None


def parse_minimal_proxy(code_hex: str | None) -> str | None:
    """Extract the implementation from EIP-1167 minimal proxy bytecode (clone)."""
    if not code_hex:
        return None
    code = code_hex[2:] if code_hex.startswith("0x") else code_hex
    for rx in (_MINIMAL_RE, _MINIMAL_RE_LOOSE):
        m = rx.search(code)
        if m:
            return addr_from_slot("0x" + m.group(1))
    return None


def detect_proxy(code_hex: str | None, read_slot: SlotReader) -> ProxyResult:
    """
    Determine the proxy standard.

    code_hex   — runtime bytecode (for EIP-1167 clones and the diamond heuristic).
    read_slot  — function that reads a storage slot of the address: slot_hex -> 32-byte word.
    """
    # 1) EIP-1167 minimal proxy — from bytecode, no slot reads
    impl = parse_minimal_proxy(code_hex)
    if impl:
        return ProxyResult(ProxyKind.EIP1167_MINIMAL, implementation=impl)

    # 2) EIP-1967 beacon
    beacon = addr_from_slot(read_slot(SLOT_1967_BEACON))
    if beacon:
        return ProxyResult(ProxyKind.BEACON, beacon=beacon,
                           admin=addr_from_slot(read_slot(SLOT_1967_ADMIN)))

    # 3) EIP-1967 impl (+ admin => transparent, otherwise UUPS)
    impl = addr_from_slot(read_slot(SLOT_1967_IMPL))
    if impl:
        admin = addr_from_slot(read_slot(SLOT_1967_ADMIN))
        kind = ProxyKind.EIP1967_TRANSPARENT if admin else ProxyKind.EIP1967_UUPS
        return ProxyResult(kind, implementation=impl, admin=admin)

    # 4) EIP-1822 UUPS legacy
    impl = addr_from_slot(read_slot(SLOT_1822))
    if impl:
        return ProxyResult(ProxyKind.EIP1822, implementation=impl)

    # 5) zeppelinos legacy slot (USDC FiatTokenProxy, etc.)
    impl = addr_from_slot(read_slot(SLOT_ZOS))
    if impl:
        return ProxyResult(ProxyKind.CUSTOM, implementation=impl)

    # 6) Diamond (EIP-2535) — heuristic on loupe/cut selectors in bytecode
    if code_hex:
        code = code_hex.lower()
        if any(sel in code for sel in DIAMOND_SELECTORS):
            return ProxyResult(ProxyKind.DIAMOND)

    return ProxyResult(ProxyKind.NONE)
