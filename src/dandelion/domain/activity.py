"""
Activity aggregation — pure core (no I/O).

From a normalized transaction list (external + internal) we compute: top callers
(co-occurrence leads), last-active, and a stratified tx sample to understand the
variety of usage (different callers + spread over time).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import norm_addr


@dataclass
class TxRow:
    hash: str
    block: int
    ts: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    method: str | None = None


def rank_callers(txs: list[TxRow], target: str, *, top: int = 10) -> list[tuple[str, int]]:
    """Who calls target most often (co-occurrence leads for the cluster)."""
    t = norm_addr(target)
    c: Counter[str] = Counter()
    for tx in txs:
        f = norm_addr(tx.from_addr)
        if f and f != t:
            c[f] += 1
    return c.most_common(top)


def last_active(txs: list[TxRow]) -> TxRow | None:
    """The most recent transaction (by block) — last-active even for rarely used contracts."""
    return max(txs, key=lambda x: x.block) if txs else None


def participants_from_trace(frames: list[dict]) -> set[str]:
    """
    All participant addresses of a transaction from its trace tree (deep co-occurrence):
    action.from / action.to of every frame + result.address for create.
    Catches contracts that co-occur but do not call the seed directly.
    """
    out: set[str] = set()
    for fr in frames or []:
        act = fr.get("action") or {}
        for key in ("from", "to"):
            a = norm_addr(act.get(key))
            if a:
                out.add(a)
        res = fr.get("result") or {}
        a = norm_addr(res.get("address"))  # created contract
        if a:
            out.add(a)
    return out


def stratified_sample(txs: list[TxRow], *, k: int = 15) -> list[str]:
    """
    A diverse sample of tx hashes: capture the variety of usage, not "the last K".
    Strategy: always the first (oldest) and last (most recent) + one per unique
    caller (different integrators/entry points), until we reach k.
    """
    if not txs:
        return []
    ordered = sorted(txs, key=lambda x: x.block)
    picked: list[str] = []
    seen_hash: set[str] = set()

    def add(tx: TxRow) -> None:
        if tx.hash and tx.hash not in seen_hash:
            seen_hash.add(tx.hash)
            picked.append(tx.hash)

    add(ordered[0])            # oldest (first use)
    add(ordered[-1])           # most recent (last-active)
    # one tx per unique caller — variety of integrators/functions
    seen_from: set[str] = set()
    for tx in ordered:
        f = norm_addr(tx.from_addr)
        key = f or tx.method or ""
        if key in seen_from:
            continue
        seen_from.add(key)
        add(tx)
        if len(picked) >= k:
            break
    return picked[:k]
