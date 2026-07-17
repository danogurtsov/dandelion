"""
Ports — abstract interfaces (Protocol) for all external I/O.

The core (`domain/`) depends only on these interfaces, not on concrete
providers. Implementations live in `adapters/`. This lets us swap the RPC,
explorer, trace system, and LLM (any key) without touching the core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# RPC
# --------------------------------------------------------------------------- #
@runtime_checkable
class RpcPort(Protocol):
    async def get_code(self, chain: int, addr: str) -> str: ...
    async def get_storage_at(self, chain: int, addr: str, slot: str) -> str: ...
    async def call(
        self,
        chain: int,
        to: str,
        data: str,
        *,
        from_: str | None = None,     # override msg.sender — "call as X"
        block: int | None = None,
    ) -> str: ...
    async def codehash(self, chain: int, addr: str) -> str | None: ...
    async def trace_transaction(self, chain: int, tx_hash: str) -> list[dict]: ...
    async def get_logs(
        self,
        chain: int,
        addr: str,
        topics: list | None = None,
        from_block: int = 0,
        to_block: str = "latest",
    ) -> list[dict]: ...
    async def get_creation(self, chain: int, addr: str) -> Creation | None: ...


@dataclass
class Creation:
    """Who deployed the contract and in which block."""
    deployer: str | None = None
    block: int | None = None
    tx: str | None = None


# --------------------------------------------------------------------------- #
# Source resolution (verified source / ABI / decompile)
# --------------------------------------------------------------------------- #
@dataclass
class SourceInfo:
    tier: str                          # SourceTier value
    name: str | None = None
    abi: list | None = None
    storage_layout: dict | None = None
    source: str | None = None


class SourceResolverPort(Protocol):
    async def resolve(self, chain: int, addr: str) -> SourceInfo | None: ...


# --------------------------------------------------------------------------- #
# Activity (tx / traces / usage) — see research/DATA_SOURCES.md
# --------------------------------------------------------------------------- #
@dataclass
class ActivityCaps:
    chains: tuple[int, ...] = ()
    supports_traces: bool = False
    supports_internal: bool = False
    supports_transfers: bool = False


@dataclass
class Deployment:
    tx: str | None = None
    block: int | None = None
    deployer: str | None = None
    factory: str | None = None


@dataclass
class TxRef:
    hash: str
    block: int
    ts: int | None = None
    from_addr: str | None = None
    method: str | None = None


@dataclass
class ActivitySummary:
    """Contract activity summary: last-active, deployer, top-callers, sample tx."""
    is_contract: bool = True
    name: str | None = None
    deployer: str | None = None
    creation_tx: str | None = None
    last_active_block: int | None = None
    last_active_ts: str | None = None
    tx_count: int | None = None
    top_callers: list[tuple[str, int]] = field(default_factory=list)
    sample_txs: list[str] = field(default_factory=list)


class ActivityPort(Protocol):
    async def summary(self, chain: int, addr: str) -> ActivitySummary | None: ...


# --------------------------------------------------------------------------- #
# LLM (optional in dandelion: classification/inference over decompiled code)
# --------------------------------------------------------------------------- #
@dataclass
class LlmMessage:
    role: str
    content: str


class LlmPort(Protocol):
    model: str

    async def complete(self, messages: list[LlmMessage], **kw) -> str: ...


# --------------------------------------------------------------------------- #
# Cache (content-addressed)
# --------------------------------------------------------------------------- #
class CachePort(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str) -> None: ...
