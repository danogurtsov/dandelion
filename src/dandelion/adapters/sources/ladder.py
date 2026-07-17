"""
Source ladder — a chain of resolvers as in predetection (fetch source OR decompile).

Order (first success wins, each step optional/graceful):
  Etherscan V2 (if a key) → Sourcify (keyless) → Blockscout (keyless) → decompile (heimdall).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ...ports import SourceInfo
from .blockscout import BlockscoutResolver
from .decompile import HeimdallDecompiler
from .etherscan_v2 import EtherscanV2Resolver
from .sourcify import SourcifyResolver


@dataclass
class SourceLadder:
    resolvers: list = field(default_factory=list)

    async def resolve(self, chain: int, addr: str, code: str | None = None) -> SourceInfo | None:
        for r in self.resolvers:
            try:
                info = await r.resolve(chain, addr, code=code)  # type: ignore[call-arg]
            except TypeError:
                info = await r.resolve(chain, addr)  # adapters without a code parameter
            if info:
                return info
        return None


def default_ladder(
    *,
    etherscan_key: str | None = None,
    use_etherscan: bool | None = None,
    decompile: bool = True,
) -> SourceLadder:
    """
    Standard chain of resolvers.

    use_etherscan controls the Etherscan step INDEPENDENTLY of whether a key is present:
      • None  (auto)  — enable if a key exists (arg or env ETHERSCAN_API_KEY);
      • True  (force) — always enable (a key is required, otherwise the step is useless);
      • False (off)   — do NOT use Etherscan even when a key is present (keyless mode:
                        Sourcify+Blockscout+decompile) — for reproducibility / saving quota.
    """
    key = etherscan_key or os.getenv("ETHERSCAN_API_KEY")
    if use_etherscan is False:
        key = None
    chain: list = []
    if key and use_etherscan is not False:
        chain.append(EtherscanV2Resolver(api_key=key))
    chain.append(SourcifyResolver())
    chain.append(BlockscoutResolver())
    if decompile:
        chain.append(HeimdallDecompiler())
    return SourceLadder(resolvers=chain)
