"""
Blockscout activity adapter (KEYLESS) — ActivityPort implementation.

Pulls from Blockscout v2 address endpoints: deployer (creator), external +
internal transactions (internal participation is indexed!), counters. Builds
an ActivitySummary via the pure aggregators in domain/activity.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from ...domain.activity import TxRow, last_active, rank_callers, stratified_sample
from ...domain.models import norm_addr
from ...ports import ActivitySummary

# chain_id -> Blockscout instance base (keyless)
BLOCKSCOUT: dict[int, str] = {
    1: "https://eth.blockscout.com",
    10: "https://optimism.blockscout.com",
    100: "https://gnosis.blockscout.com",
    137: "https://polygon.blockscout.com",
    8453: "https://base.blockscout.com",
    42161: "https://arbitrum.blockscout.com",
    534352: "https://scroll.blockscout.com",
}


def _hash_of(v: Any) -> str | None:
    """Blockscout returns from/to either as {'hash': '0x..'} or as a string."""
    if isinstance(v, dict):
        return v.get("hash")
    return v if isinstance(v, str) else None


def parse_address_info(data: dict) -> dict:
    return {
        "name": data.get("name"),
        "is_contract": bool(data.get("is_contract", True)),
        "deployer": norm_addr(_hash_of(data.get("creator_address_hash"))),
        "creation_tx": data.get("creation_tx_hash"),
    }


def parse_tx_items(data: dict) -> list[TxRow]:
    rows: list[TxRow] = []
    for it in (data.get("items") or []):
        blk = it.get("block_number") or it.get("block")
        rows.append(TxRow(
            hash=it.get("hash") or it.get("transaction_hash") or "",
            block=int(blk) if blk is not None else 0,
            ts=it.get("timestamp"),
            from_addr=_hash_of(it.get("from")),
            to_addr=_hash_of(it.get("to")),
            method=it.get("method"),
        ))
    return rows


@dataclass
class BlockscoutActivity:
    timeout: float = 20.0

    async def _get(self, client: httpx.AsyncClient, url: str) -> dict:
        try:
            r = await client.get(url, headers={"User-Agent": "dandelion"})
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return {}

    async def deployer(self, chain: int, addr: str) -> str | None:
        """Lightweight deployer lookup (1 call) — for deployer-closure over candidates."""
        base = BLOCKSCOUT.get(chain)
        if not base:
            return None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            info = await self._get(client, f"{base}/api/v2/addresses/{addr}")
        return parse_address_info(info).get("deployer") if info else None

    async def deployments_by(self, chain: int, deployer: str, *, cap: int = 40) -> list[str]:
        """Contracts deployed by an address (created_contract in its transactions). Keyless."""
        base = BLOCKSCOUT.get(chain)
        if not base:
            return []
        out: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            data = await self._get(client, f"{base}/api/v2/addresses/{deployer}/transactions?filter=from")
        for it in (data.get("items") or []):
            cc = it.get("created_contract")
            h = cc.get("hash") if isinstance(cc, dict) else cc
            a = norm_addr(h)
            if a and a not in out:
                out.append(a)
            if len(out) >= cap:
                break
        return out

    async def summary(self, chain: int, addr: str) -> ActivitySummary | None:
        base = BLOCKSCOUT.get(chain)
        if not base:
            return None
        a = f"{base}/api/v2/addresses/{addr}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            info_j, txs_j, int_j, cnt_j = await asyncio.gather(
                self._get(client, a),
                self._get(client, f"{a}/transactions"),
                self._get(client, f"{a}/internal-transactions"),
                self._get(client, f"{a}/counters"),
            )
        if not (info_j or txs_j or int_j):
            return None

        info = parse_address_info(info_j)
        rows = parse_tx_items(txs_j) + parse_tx_items(int_j)
        la = last_active(rows)
        try:
            tx_count = int(cnt_j.get("transactions_count")) if cnt_j.get("transactions_count") else None
        except (TypeError, ValueError):
            tx_count = None

        return ActivitySummary(
            is_contract=info["is_contract"],
            name=info["name"],
            deployer=info["deployer"],
            creation_tx=info["creation_tx"],
            last_active_block=la.block if la else None,
            last_active_ts=la.ts if la else None,
            tx_count=tx_count,
            top_callers=rank_callers(rows, addr, top=8),
            sample_txs=stratified_sample(rows, k=15),
        )
