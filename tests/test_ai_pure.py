"""Pure AI-layer helpers: opaque routing, selector extraction, agreement stats."""
from dandelion.domain.agreement import cohen_kappa, simple_agreement
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    NodeType,
    SourceTier,
)
from dandelion.domain.routing import is_opaque, opaque_keys
from dandelion.domain.selectors import extract_selectors


# --- routing ---------------------------------------------------------------- #
def test_is_opaque():
    bc = ContractNode(address="0x" + "11" * 20, chain_id=1,
                      source_tier=SourceTier.BYTECODE_ONLY, node_type=NodeType.POOL)
    verified_known = ContractNode(address="0x" + "22" * 20, chain_id=1,
                                  source_tier=SourceTier.VERIFIED, node_type=NodeType.POOL)
    unknown = ContractNode(address="0x" + "33" * 20, chain_id=1,
                           source_tier=SourceTier.VERIFIED, node_type=NodeType.UNKNOWN)
    assert is_opaque(bc) and is_opaque(unknown) and not is_opaque(verified_known)


def test_opaque_keys_skips_external_and_flags_empty_factory():
    g = ArchitectureGraph()
    fac = ContractNode(address="0x" + "aa" * 20, chain_id=1, node_type=NodeType.FACTORY,
                       source_tier=SourceTier.VERIFIED)              # verified but no instances
    ext = ContractNode(address="0x" + "bb" * 20, chain_id=1, node_type=NodeType.UNKNOWN)
    ext.membership = "external"
    g.add_node(fac)
    g.add_node(ext)
    keys = opaque_keys(g)
    assert fac.key in keys           # factory with no enumerated instances = stalled
    assert ext.key not in keys       # external is never a target


# --- selectors -------------------------------------------------------------- #
def test_extract_selectors_finds_push4():
    # PUSH4 0x0dfe1681 (token0) ... PUSH1 0x60 (should be skipped, not read as selector)
    code = "0x" + "630dfe1681" + "6060" + "63d21220a7"
    sels = extract_selectors(code)
    assert "0x0dfe1681" in sels and "0xd21220a7" in sels


def test_extract_selectors_skips_push_immediates():
    # a PUSH4 whose bytes appear inside a PUSH32 immediate must not be mis-extracted
    code = "0x" + "7f" + "63aabbccdd" + "00" * 27      # PUSH32 with a fake selector inside
    assert "0x63aabbcc" not in extract_selectors(code)


def test_extract_selectors_empty():
    assert extract_selectors(None) == [] and extract_selectors("0x") == []


# --- agreement -------------------------------------------------------------- #
def test_cohen_kappa_perfect_and_chance():
    assert cohen_kappa([True, False, True], [True, False, True]) == 1.0
    # opposite raters → negative/zero
    assert cohen_kappa([True, True, False, False], [False, False, True, True]) < 0.5
    assert simple_agreement([True, False], [True, True]) == 0.5


def test_cohen_kappa_empty():
    assert cohen_kappa([], []) == 1.0
