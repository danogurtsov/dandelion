"""
Blockscout source resolver (keyless) — SourceResolverPort implementation.

GET /api/v2/smart-contracts/{addr} → name + abi for verified contracts.
Coverage: eth/optimism/arbitrum/base/gnosis/polygon (best-effort).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ...ports import SourceInfo

# chain_id -> Blockscout instance base
BLOCKSCOUT: dict[int, str] = {
    1: "https://eth.blockscout.com",
    10: "https://optimism.blockscout.com",
    100: "https://gnosis.blockscout.com",
    137: "https://polygon.blockscout.com",
    8453: "https://base.blockscout.com",
    42161: "https://arbitrum.blockscout.com",
    534352: "https://scroll.blockscout.com",
}


def parse_blockscout(data: dict) -> SourceInfo | None:
    """Pure parser for /api/v2/smart-contracts/{addr} → SourceInfo."""
    if not data.get("is_verified") and not data.get("name"):
        return None
    name = data.get("name") or None
    abi = data.get("abi")
    if not name and not abi:
        return None
    return SourceInfo(tier="verified", name=name, abi=abi)


@dataclass
class BlockscoutResolver:
    timeout: float = 20.0

    async def resolve(self, chain: int, addr: str, code: str | None = None) -> SourceInfo | None:
        base = BLOCKSCOUT.get(chain)
        if not base:
            return None
        url = f"{base}/api/v2/smart-contracts/{addr}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, headers={"User-Agent": "dandelion"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return parse_blockscout(r.json())
        except Exception:  # noqa: BLE001
            return None
