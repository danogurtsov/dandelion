"""
Factory-instance enumeration from logs — pure core (no I/O).

Factories spawn instances via `Create*` events without a getter list (Morpho vaults,
Uniswap pairs, …). Heuristic (no hardcoded signatures): in the logs of the dominant event
the CREATED instance = the address that is UNIQUE per event (new every time); tokens/factory/
caller repeat across logs → filtered out. Works for both indexed topics and data.
"""
from __future__ import annotations

from collections import Counter

from .reads import decode_address_strict

# Curated registry of topic0 for Create* events of factories/singletons (keccak256 precomputed,
# the domain stays stdlib-pure). Used as a getLogs topic filter: "hot" singletons
# (Morpho Blue — millions of logs) only respond to creation events, otherwise getLogs hangs.
CREATE_EVENT_TOPICS: dict[str, str] = {
    "0xac4b2400f169220b0c0afdde7a0b32e775ba727ea1cb30b35f935cdaab8683ac": "CreateMarket",
    "0xed8c95d05909b0f217f3e68171ef917df4b278d5addfe4dda888e90279be7d1d": "CreateMetaMorpho",
    "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9": "PairCreated",
    "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118": "PoolCreated",
    "0x8aafde3cf840637d87b61c9e50dc3bf60866b3a38bb00887610ce48402adc894": "MarketCreated",
    "0x09e48df7857bd0c1e0d31bb8a85d42cf1874817895f171c917f6ee2cea73ec20": "Deployed",
    "0x00fffc2da0b561cae30d9826d37709e9421c4725faebc226cbbb7ef5fc5e7349": "ProxyCreated",
    "0xcf78cf0d6f3d8371e1075c69c492ab4ec5d8cf23a1a239b6a51a1d00be7ca312": "ContractCreated",
    "0x0b045af6aff86dd2cda5342fd0329a354dc66759ff1eda00d7ecf13a76c7fb3b": "VaultCreated",
    "0x117c72e6c25f0a072e36e148df71468ce2f3dbe7defec5b2c257a6e3eb65278c": "InstanceDeployed",
}


def create_event_topics() -> list[str]:
    """topic0 hashes of all known Create* events (for an OR filter on getLogs at position 0)."""
    return list(CREATE_EVENT_TOPICS)


def _words(log: dict) -> list[str]:
    """All 32-byte words of a log: indexed topics (except topic0) + data."""
    out: list[str] = list((log.get("topics") or [])[1:])
    data = log.get("data") or ""
    d = data[2:] if data.startswith("0x") else data
    out += ["0x" + d[i:i + 64] for i in range(0, len(d), 64)]
    return out


def created_addresses_from_logs(logs: list[dict], *, cap: int = 120) -> list[str]:
    """
    Instance addresses created by a factory (from its logs). None-safe, pure.
    Take the dominant event (most frequent topic0), collect address-shaped words,
    instances = those appearing in EXACTLY one log (unique per creation).
    """
    if not logs:
        return []
    ev_count = Counter(lg["topics"][0] for lg in logs if lg.get("topics"))
    if not ev_count:
        return []
    dominant = ev_count.most_common(1)[0][0]
    ev = [lg for lg in logs if lg.get("topics") and lg["topics"][0] == dominant]

    occ: Counter[str] = Counter()
    for lg in ev:
        seen_in_log: set[str] = set()
        for w in _words(lg):
            a = decode_address_strict(w)
            if a and a not in seen_in_log:
                seen_in_log.add(a)
                occ[a] += 1
    # instance = unique per event (a new contract on each create); tokens/factory repeat
    out = [a for a, c in occ.items() if c == 1]
    return out[:cap]
