"""
JSON-RPC adapter (async, httpx) — RpcPort implementation.

Provider-agnostic: a {chain_id: rpc_url} map. Supports eth_call with a `from`
override (checking "can X call Y"). codehash = keccak(code).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from ...ports import Creation


def _keccak(data: bytes) -> str:
    # lazy import: eth-utils comes transitively with web3
    from eth_utils import keccak  # type: ignore
    return "0x" + keccak(data).hex()


@dataclass
class JsonRpcClient:
    rpc_urls: dict[int, str]
    timeout: float = 30.0
    _id: int = field(default=0, init=False)
    # cache of immutable data (contract code never changes) — eliminates repeat fetches
    _code_cache: dict[tuple[int, str], str] = field(default_factory=dict, init=False)

    async def _rpc(self, chain: int, method: str, params: list[Any]) -> Any:
        url = self.rpc_urls.get(chain)
        if not url:
            raise ValueError(f"no rpc url for chain {chain}")
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            body = r.json()
        if "error" in body and body["error"]:
            raise RuntimeError(f"rpc {method} error: {body['error']}")
        return body.get("result")

    async def get_code(self, chain: int, addr: str) -> str:
        key = (chain, addr.lower())
        cached = self._code_cache.get(key)
        if cached is not None:
            return cached
        code = await self._rpc(chain, "eth_getCode", [addr, "latest"]) or "0x"
        self._code_cache[key] = code
        return code

    async def get_storage_at(self, chain: int, addr: str, slot: str) -> str:
        return await self._rpc(chain, "eth_getStorageAt", [addr, slot, "latest"]) or "0x" + "0" * 64

    async def call(
        self,
        chain: int,
        to: str,
        data: str,
        *,
        from_: str | None = None,
        block: int | None = None,
    ) -> str:
        tx: dict[str, str] = {"to": to, "data": data}
        if from_:
            tx["from"] = from_
        blk = hex(block) if block is not None else "latest"
        return await self._rpc(chain, "eth_call", [tx, blk]) or "0x"

    async def codehash(self, chain: int, addr: str) -> str | None:
        code = await self.get_code(chain, addr)
        if not code or code == "0x":
            return None
        return _keccak(bytes.fromhex(code[2:]))

    async def trace_transaction(self, chain: int, tx_hash: str) -> list[dict]:
        return await self._rpc(chain, "trace_transaction", [tx_hash]) or []

    async def get_logs(
        self,
        chain: int,
        addr: str,
        topics: list | None = None,
        from_block: int = 0,
        to_block: str = "latest",
    ) -> list[dict]:
        flt = {
            "address": addr,
            "fromBlock": hex(from_block),
            "toBlock": to_block,
            "topics": topics or [],
        }
        return await self._rpc(chain, "eth_getLogs", [flt]) or []

    async def get_creation(self, chain: int, addr: str) -> Creation | None:
        # Otterscan-compatible method; if the node doesn't support it — gracefully None
        try:
            res = await self._rpc(chain, "ots_getContractCreator", [addr])
        except Exception:
            return None
        if not res:
            return None
        return Creation(deployer=res.get("creator"), tx=res.get("hash"))
