"""
CompositeActivity — a chain of activity adapters (first non-empty response wins).

Blockscout keyless covers 7 chains (internal-txs/top-callers/deployments_by); Etherscan V2
supplies the deployer on the rest (Sonic/exotic) and acts as a fallback for gaps. The order is
set by the constructor: usually [Blockscout, Etherscan]. Each method walks the adapters gracefully.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...ports import ActivitySummary


@dataclass
class CompositeActivity:
    providers: list = field(default_factory=list)

    async def summary(self, chain: int, addr: str) -> ActivitySummary | None:
        best: ActivitySummary | None = None
        for p in self.providers:
            try:
                s = await p.summary(chain, addr)
            except Exception:  # noqa: BLE001
                s = None
            if s is None:
                continue
            if best is None:
                best = s
            # enrich with the deployer from the next provider if the first one lacks it
            if not best.deployer and s.deployer:
                best.deployer = s.deployer
            if best.top_callers and best.deployer:
                break
        return best

    async def deployer(self, chain: int, addr: str) -> str | None:
        for p in self.providers:
            if not hasattr(p, "deployer"):
                continue
            try:
                d = await p.deployer(chain, addr)
            except Exception:  # noqa: BLE001
                d = None
            if d:
                return d
        return None

    async def deployments_by(self, chain: int, deployer: str, *, cap: int = 40) -> list[str]:
        for p in self.providers:
            if not hasattr(p, "deployments_by"):
                continue
            try:
                out = await p.deployments_by(chain, deployer, cap=cap)
            except Exception:  # noqa: BLE001
                out = []
            if out:
                return out
        return []
