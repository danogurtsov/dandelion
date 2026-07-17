"""
Co-occurrence — pure core.

For address X: which neighboring addresses most often appear alongside it in the same
transaction/trace. High frequency is a strong lead for a link and a shared cluster.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .models import norm_addr


def rank_neighbors(
    traces: Iterable[Iterable[str]],
    target: str,
    *,
    top: int = 20,
) -> list[tuple[str, int]]:
    """
    traces  — a set of traces/transactions, each = a list of participant addresses.
    target  — the address of interest.
    Returns [(neighbor, count)], descending by frequency of co-occurrence with target.
    """
    t = norm_addr(target)
    counts: Counter[str] = Counter()
    for tr in traces:
        addrs = {na for a in tr if (na := norm_addr(a)) is not None}
        if t in addrs:
            for a in addrs:
                if a != t:
                    counts[a] += 1
    return counts.most_common(top)


def strong_neighbors(
    ranked: list[tuple[str, int]],
    *,
    min_count: int = 3,
    min_ratio: float = 0.2,
) -> list[str]:
    """
    Select "strong" neighbors: appeared at least min_count times AND at least
    min_ratio of the top neighbor's frequency. These are leads for cluster membership.
    """
    if not ranked:
        return []
    top_count = ranked[0][1]
    threshold = max(min_count, top_count * min_ratio)
    return [a for a, c in ranked if c >= threshold]
