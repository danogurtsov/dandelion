"""
Etherscan V2 activity adapter (key required) — deployer via getcontractcreation.

Closes the ots gap: dRPC does not support `ots_getContractCreator`, and Blockscout keyless
does not cover every chain (Sonic/exotic). Etherscan V2 is multi-chain by chainid, batching up to 5 addresses.
Partially implements ActivityPort: deployer/creations_batch; summary is minimal (deployer only).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from ...domain.models import norm_addr
from ...ports import ActivitySummary

_ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"


def parse_creations(result) -> dict[str, str | None]:
    """result[] getcontractcreation → {contractAddress: contractCreator}."""
    out: dict[str, str | None] = {}
    if isinstance(result, list):
        for it in result:
            a = norm_addr(it.get("contractAddress"))
            c = norm_addr(it.get("contractCreator"))
            if a:
                out[a] = c
    return out


@dataclass
class EtherscanActivity:
    api_key: str | None = None
    base: str = _ETHERSCAN_V2
    timeout: float = 20.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("ETHERSCAN_API_KEY")

    async def _get(self, params: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(self.base, params=params, headers={"User-Agent": "dandelion"})
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return {}

    async def creations_batch(self, chain: int, addrs: list[str]) -> dict[str, str | None]:
        """Deployers for a batch of addresses (up to 5 per request) — {addr: creator}."""
        if not self.api_key or not addrs:
            return {}
        out: dict[str, str | None] = {}
        for i in range(0, len(addrs), 5):
            chunk = addrs[i:i + 5]
            body = await self._get({
                "chainid": str(chain), "module": "contract", "action": "getcontractcreation",
                "contractaddresses": ",".join(chunk), "apikey": self.api_key,
            })
            out.update(parse_creations(body.get("result")))
        return out

    async def deployer(self, chain: int, addr: str) -> str | None:
        """Deployer of a single contract (getcontractcreation)."""
        got = await self.creations_batch(chain, [addr])
        return got.get(norm_addr(addr))

    async def deployments_by(self, chain: int, deployer: str, *, cap: int = 40) -> list[str]:
        """Not cheap to support via the Etherscan path (needs a txlist scan) — Blockscout covers this."""
        return []

    async def summary(self, chain: int, addr: str) -> ActivitySummary | None:
        dep = await self.deployer(chain, addr)
        if not dep:
            return None
        return ActivitySummary(is_contract=True, deployer=dep)
