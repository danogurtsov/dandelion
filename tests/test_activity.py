"""Unit tests for activity: pure aggregators + Blockscout parsers (no network)."""
from dandelion.adapters.activity.blockscout import parse_address_info, parse_tx_items
from dandelion.domain.activity import TxRow, last_active, rank_callers, stratified_sample
from dandelion.domain.models import norm_addr

X = "0x" + "e" * 40
C1 = "0x" + "1" * 40
C2 = "0x" + "2" * 40


def _tx(h, blk, frm):
    return TxRow(hash=h, block=blk, from_addr=frm, to_addr=X)


# --- pure aggregators ---
def test_rank_callers_excludes_target():
    txs = [_tx("a", 1, C1), _tx("b", 2, C1), _tx("c", 3, C2), _tx("d", 4, X)]
    ranked = dict(rank_callers(txs, X))
    assert ranked[norm_addr(C1)] == 2 and ranked[norm_addr(C2)] == 1
    assert norm_addr(X) not in ranked   # the target itself is not counted as a caller


def test_last_active_by_block():
    txs = [_tx("a", 10, C1), _tx("b", 99, C2), _tx("c", 50, C1)]
    assert last_active(txs).block == 99


def test_stratified_sample_diverse_and_bounded():
    txs = [_tx(f"h{i}", i, C1 if i % 2 else C2) for i in range(30)]
    s = stratified_sample(txs, k=5)
    assert len(s) <= 5
    assert "h0" in s and "h29" in s       # oldest and newest are always included


def test_stratified_sample_empty():
    assert stratified_sample([], k=5) == []


# --- Blockscout parsers ---
def test_parse_address_info():
    data = {"name": "InstaTimelock", "is_contract": True,
            "creator_address_hash": {"hash": C1}, "creation_tx_hash": "0xabc"}
    info = parse_address_info(data)
    assert info["name"] == "InstaTimelock"
    assert info["deployer"] == norm_addr(C1)
    assert info["creation_tx"] == "0xabc"


def test_parse_tx_items_dict_and_str_addr():
    data = {"items": [
        {"hash": "0x1", "block_number": 100, "from": {"hash": C1}, "to": {"hash": X}, "method": "exec"},
        {"transaction_hash": "0x2", "block_number": 101, "from": C2, "to": X},   # internal-style
    ]}
    rows = parse_tx_items(data)
    assert len(rows) == 2
    assert rows[0].from_addr == C1 and rows[0].block == 100 and rows[0].method == "exec"
    assert rows[1].hash == "0x2" and rows[1].from_addr == C2


def test_participants_from_trace():
    from dandelion.domain.activity import participants_from_trace
    frames = [
        {"action": {"from": C1, "to": X}, "type": "call"},
        {"action": {"from": X, "to": C2}, "type": "call"},
        {"action": {"from": C1}, "result": {"address": "0x" + "9" * 40}, "type": "create"},
    ]
    p = participants_from_trace(frames)
    assert norm_addr(C1) in p and norm_addr(C2) in p and norm_addr(X) in p
    assert norm_addr("0x" + "9" * 40) in p   # the created contract
