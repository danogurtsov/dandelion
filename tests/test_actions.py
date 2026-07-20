"""Typed LLM action schema: parsing + per-kind signature validation."""
from dandelion.domain.actions import Action, parse_actions


def test_valid_actions_parsed():
    items = [
        {"key": "1:0xaa", "kind": "read_addr", "sig": "priceOracle()", "purpose": "struct"},
        {"key": "1:0xbb", "kind": "read_addr_array", "sig": "getReservesList()", "purpose": "asset"},
        {"key": "1:0xcc", "kind": "enumerate_index", "sig": "coins(uint256)", "purpose": "asset", "cap": 8},
        {"key": "1:0xdd", "kind": "reserve_keyed", "sig": "getReserveData(address)", "purpose": "struct"},
    ]
    acts = parse_actions(items)
    assert len(acts) == 4
    assert acts[2].name == "coins" and acts[2].cap == 8
    assert acts[0].purpose == "struct"


def test_wrong_kind_dropped():
    assert parse_actions([{"key": "1:0xaa", "kind": "delete_node", "sig": "x()"}]) == []


def test_signature_shape_enforced_per_kind():
    # enumerate_index requires an index arg; a no-arg sig is rejected
    assert parse_actions([{"key": "1:0xaa", "kind": "enumerate_index", "sig": "coins()"}]) == []
    # reserve_keyed requires (address)
    assert parse_actions([{"key": "1:0xaa", "kind": "reserve_keyed", "sig": "getReserveData(uint256)"}]) == []
    # read_addr must be no-arg
    assert parse_actions([{"key": "1:0xaa", "kind": "read_addr", "sig": "owner(address)"}]) == []


def test_smuggled_args_and_extra_text_rejected():
    # an injected multi-call / prose is not a clean single sig
    assert parse_actions([{"key": "1:0xaa", "kind": "read_addr",
                           "sig": "owner() then transfer(x)"}]) == []


def test_missing_key_dropped():
    assert parse_actions([{"kind": "read_addr", "sig": "owner()"}]) == []


def test_purpose_defaults_and_cap_bounds():
    a = parse_actions([{"key": "1:0xaa", "kind": "read_addr", "sig": "owner()", "cap": 999}])[0]
    assert isinstance(a, Action) and a.purpose == "generic" and a.cap == 60
