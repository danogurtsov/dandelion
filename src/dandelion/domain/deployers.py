"""
Common deployers — pure core.

Deployer clustering: contracts from the same deployer are candidates for one project.
BUT "common" deployers (deterministic factories, Safe factories, CreateX, etc.)
deploy for everyone — they cannot be used as a membership signal.
"""
from __future__ import annotations

from .models import norm_addr

# known common deployers / factories (lowercase) — NOT a membership signal
COMMON_DEPLOYERS: set[str] = {
    "0x4e59b44847b379578588920ca78fbf26c0b4956c",  # Arachnid deterministic deployment proxy
    "0x7a0d94f55792c434d74a40883c6ed8545e406d12",  # deterministic deployer (alt)
    "0x0000000000ffe8b47b3e2130213b802212439497",  # immutable CREATE2 factory
    "0xba5ed099633d3b313e4d5f7bdc1305d3c28ba5ed",  # CreateX
    "0xa6b71e26c5e0845f74c812102ca7114b6a896ab2",  # Safe SafeProxyFactory 1.3.0
    "0x4e1dcf7ad4e460cfd30791ccc4f9c8a4f820ec67",  # Safe SafeProxyFactory 1.4.1
    "0x76e2cfc1f5fa8f6a5b3fc4c8f4788f0116861f9b",  # GnosisSafeProxyFactory 1.1.1
    "0xc22834581ebc8527d974f8a1c97e1bea4ef910bc",  # GnosisSafeProxyFactory 1.3.0 (alt net)
    "0x914d7fec6aac8cd542e72bca78b30650d45643d7",  # EIP-1167 clone factory (openzeppelin era)
}


def is_common_deployer(addr: str | None) -> bool:
    """True if the address is a common deployer/factory (not a project-membership signal)."""
    a = norm_addr(addr)
    return a in COMMON_DEPLOYERS if a else False
