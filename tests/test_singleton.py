"""
Singleton-parsing tests: CreateMarket-like Morpho Blue events.

A market = bytes32 storage (no address). The event carries value-referenced dependencies:
loanToken/collateralToken/oracle/irm. Tokens+IRM are reused across markets (→ nodes),
while the oracle is unique per market (→ only in logical.refs, never becomes a node).
"""
from dandelion.domain.singleton import (
    SINGLETON_TOPICS,
    dominant_topic0,
    logical_entities_from_logs,
    referenced_addresses_from_logs,
)

CREATE_MARKET = "0xac4b2400f169220b0c0afdde7a0b32e775ba727ea1cb30b35f935cdaab8683ac"


def _word(b: str) -> str:
    """32-byte word with address b*20 (upper 12 bytes zero, top byte of address non-zero)."""
    return "0" * 24 + b * 20


def _addr(b: str) -> str:
    return "0x" + b * 20


def _market_log(mkt_id: str, loan: str, coll: str, oracle: str, irm: str, lltv: str) -> dict:
    # data = loanToken, collateralToken, oracle, irm, lltv(uint) — as in Morpho MarketParams
    data = "0x" + _word(loan) + _word(coll) + _word(oracle) + _word(irm) + ("0" * 63 + lltv)
    return {"topics": [CREATE_MARKET, mkt_id], "data": data}


# three markets: shared loan(aa)/coll(bb)/irm(dd) — reusable; oracle is unique per market
LOGS = [
    _market_log("0x" + "01" * 32, "aa", "bb", "c1", "dd", "1"),
    _market_log("0x" + "02" * 32, "aa", "bb", "c2", "dd", "1"),
    _market_log("0x" + "03" * 32, "aa", "bb", "c3", "dd", "1"),
]


def test_dominant_topic0_is_singleton():
    assert dominant_topic0(LOGS) == CREATE_MARKET
    assert dominant_topic0(LOGS) in SINGLETON_TOPICS


def test_referenced_returns_only_recurring():
    # min_count=3: loan/coll/irm appear in 3 logs → nodes; oracle (once) filtered out
    got = set(referenced_addresses_from_logs(LOGS, min_count=3))
    assert got == {_addr("aa"), _addr("bb"), _addr("dd")}
    for uniq in ("c1", "c2", "c3"):
        assert _addr(uniq) not in got


def test_referenced_min_count_lower_includes_oracles():
    got = set(referenced_addresses_from_logs(LOGS, min_count=1))
    assert _addr("c1") in got and _addr("dd") in got


def test_logical_entities_capture_markets_and_refs():
    ents = logical_entities_from_logs(LOGS)
    assert len(ents) == 3
    ids = {e["id"] for e in ents}
    assert ids == {"0x" + "01" * 32, "0x" + "02" * 32, "0x" + "03" * 32}
    # the first market's refs include its unique oracle c1 (kept even without a node)
    first = next(e for e in ents if e["id"] == "0x" + "01" * 32)
    assert _addr("c1") in first["refs"]
    assert _addr("aa") in first["refs"] and _addr("dd") in first["refs"]


def test_logical_entities_cap():
    assert len(logical_entities_from_logs(LOGS, cap=2)) == 2


def test_empty_logs_safe():
    assert referenced_addresses_from_logs([]) == []
    assert logical_entities_from_logs([]) == []
    assert dominant_topic0([]) == ""
