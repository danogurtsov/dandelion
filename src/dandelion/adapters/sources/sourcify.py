"""
Sourcify source resolver (keyless) — SourceResolverPort implementation.

Sourcify v2 API: GET /v2/contract/<chainId>/<address>?fields=metadata
→ Solidity metadata (contract name from compilationTarget, ABI from output.abi).
404 = not verified.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ...ports import SourceInfo


def parse_sourcify(data: dict) -> SourceInfo | None:
    """Pure parser for a Sourcify v2 response → SourceInfo (testable without the network)."""
    md = data.get("metadata") or {}
    ct = md.get("settings", {}).get("compilationTarget", {})
    name = next(iter(ct.values()), None) if ct else None
    abi = md.get("output", {}).get("abi")
    if not name and not abi:
        return None
    return SourceInfo(tier="verified", name=name, abi=abi)


@dataclass
class SourcifyResolver:
    base: str = "https://sourcify.dev/server"
    timeout: float = 20.0

    async def resolve(self, chain: int, addr: str) -> SourceInfo | None:
        url = f"{self.base}/v2/contract/{chain}/{addr}?fields=metadata"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, headers={"User-Agent": "dandelion"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return parse_sourcify(r.json())
        except Exception:  # noqa: BLE001 — the source is optional, degrade silently
            return None
