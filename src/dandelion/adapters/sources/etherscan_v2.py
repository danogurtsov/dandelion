"""
Etherscan V2 source resolver (optional API key) — SourceResolverPort implementation.

One key, multi-chain via chainid. GET getsourcecode → ContractName/ABI/Proxy/Implementation.
The key is optional: if unset, the adapter is not used (see ladder).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

from ...ports import SourceInfo

_ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"


def parse_etherscan(result: dict) -> SourceInfo | None:
    """Pure parser for the getsourcecode.result[0] element → SourceInfo."""
    name = (result.get("ContractName") or "").strip() or None
    abi_raw = result.get("ABI") or ""
    abi = None
    if abi_raw and abi_raw != "Contract source code not verified":
        try:
            abi = json.loads(abi_raw)
        except (json.JSONDecodeError, TypeError):
            abi = None
    source = result.get("SourceCode") or None
    if not name and not abi:
        return None
    return SourceInfo(tier="verified", name=name, abi=abi, source=source)


@dataclass
class EtherscanV2Resolver:
    api_key: str | None = None
    base: str = _ETHERSCAN_V2
    timeout: float = 20.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("ETHERSCAN_API_KEY")

    async def resolve(self, chain: int, addr: str, code: str | None = None) -> SourceInfo | None:
        if not self.api_key:
            return None
        params = {
            "chainid": str(chain), "module": "contract", "action": "getsourcecode",
            "address": addr, "apikey": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(self.base, params=params, headers={"User-Agent": "dandelion"})
            r.raise_for_status()
            body = r.json()
            res = body.get("result")
            if isinstance(res, list) and res:
                return parse_etherscan(res[0])
        except Exception:  # noqa: BLE001
            return None
        return None
