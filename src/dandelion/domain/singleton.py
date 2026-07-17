"""
Singleton-event parsing — pure core (no I/O).

A singleton (Morpho Blue) holds "markets" as bytes32 storage: they are NOT contracts,
but `CreateMarket` events contain value-referenced dependencies (oracle/irm/tokens).
We extract: (a) referenced addresses = real dependency nodes (including recurring ones —
oracles are reused), (b) logical entities = the markets themselves (id + refs).
"""
from __future__ import annotations

from collections import Counter

from .reads import decode_address_strict

# topic0 of events where the "created" thing = a bytes32 market (not a contract): its instance
# has no address, and the data words are value-referenced dependencies (oracle/irm/tokens).
# Distinguishes a singleton from a factory: a factory's created address is unique-per-event (a new
# contract), whereas here a "unique" oracle is just a per-market reference to a PRE-existing
# contract, so it goes into logical.refs, not into nodes.
SINGLETON_TOPICS: frozenset[str] = frozenset({
    "0xac4b2400f169220b0c0afdde7a0b32e775ba727ea1cb30b35f935cdaab8683ac",  # CreateMarket (Morpho Blue)
    "0x8aafde3cf840637d87b61c9e50dc3bf60866b3a38bb00887610ce48402adc894",  # MarketCreated
})


def dominant_topic0(logs: list[dict]) -> str:
    """topic0 of the most frequent event in the log set ('' if empty)."""
    return _dominant_logs(logs)[0]


def _dominant_logs(logs: list[dict]) -> tuple[str, list[dict]]:
    ev = Counter(lg["topics"][0] for lg in logs if lg.get("topics"))
    if not ev:
        return "", []
    top = ev.most_common(1)[0][0]
    return top, [lg for lg in logs if lg.get("topics") and lg["topics"][0] == top]


def _addr_words(log: dict) -> list[str]:
    out = [decode_address_strict(t) for t in (log.get("topics") or [])[1:]]
    data = log.get("data") or ""
    d = data[2:] if data.startswith("0x") else data
    out += [decode_address_strict("0x" + d[i:i + 64]) for i in range(0, len(d), 64)]
    return [a for a in out if a]


def referenced_addresses_from_logs(logs: list[dict], *, min_count: int = 3, cap: int = 40) -> list[str]:
    """
    REUSED dependencies from events (IRM/tokens — shared across many markets).
    Only addresses seen ≥ min_count times → shared components become nodes, while
    per-market instances (one oracle per market, 1261 of them) do NOT bloat the graph
    (they live in logical.refs).
    """
    _, ev = _dominant_logs(logs)
    occ: Counter[str] = Counter()
    for lg in ev:
        for a in set(_addr_words(lg)):
            occ[a] += 1
    return [a for a, c in occ.most_common(cap) if c >= min_count]


def logical_entities_from_logs(logs: list[dict], *, cap: int = 80) -> list[dict]:
    """
    Logical entities (markets) of the dominant event: id = indexed topic1, refs = addresses from data.
    Returns [{"id": <hex>, "refs": [addr,…]}], without an address for the entity itself.
    """
    _, ev = _dominant_logs(logs)
    out: list[dict] = []
    for lg in ev:
        tp = lg.get("topics") or []
        ident = tp[1] if len(tp) >= 2 else None
        refs = _addr_words(lg)
        if ident and refs:
            out.append({"id": ident, "refs": refs})
        if len(out) >= cap:
            break
    return out
