"""Unit tests for clone collapsing — protection against combinatorial explosion."""
from dandelion.domain.clones import collapse_clones
from dandelion.domain.models import ContractNode, NodeType


def _pair(i: int, codehash: str, scope: bool = False) -> ContractNode:
    addr = "0x" + f"{i:040x}"
    return ContractNode(address=addr, chain_id=1, codehash=codehash, is_scope=scope)


def test_large_group_collapses_with_cap():
    same = "0x" + "ab" * 32
    nodes = [_pair(i, same) for i in range(1000)]
    kept, classes = collapse_clones(nodes, cap=50, min_group=4)

    assert len(classes) == 1
    cls = classes[0]
    assert cls.total_count == 1000
    assert len(cls.sampled) == 50
    assert cls.capped is True
    # kept retains only 50 samples, not 1000
    assert len(kept) == 50


def test_small_group_kept_individually():
    same = "0x" + "cd" * 32
    nodes = [_pair(i, same) for i in range(3)]        # < min_group
    kept, classes = collapse_clones(nodes, cap=50, min_group=4)
    assert classes == []
    assert len(kept) == 3


def test_scope_nodes_never_collapsed():
    same = "0x" + "ef" * 32
    nodes = [_pair(i, same, scope=True) for i in range(1000)]
    kept, classes = collapse_clones(nodes, cap=50, min_group=4)
    assert classes == []
    assert len(kept) == 1000


def test_registration_and_factory_attached():
    same = "0x" + "12" * 32
    nodes = [_pair(i, same) for i in range(10)]
    fac = {n.address: "0x" + "fa" * 20 for n in nodes}
    # with factory_of, the grouping key = fac:<chain>:<factory>:<type>
    reg = {f"fac:1:{'0x' + 'fa' * 20}:unknown": "factory.createPair -> PairCreated"}
    _, classes = collapse_clones(nodes, cap=5, min_group=4,
                                 factory_of=fac, registration_of=reg)
    assert classes[0].registration == "factory.createPair -> PairCreated"
    assert classes[0].factory == "0x" + "fa" * 20
    assert classes[0].node_type == NodeType.CLONE_CLASS


def test_factory_collapse_by_logic_identity():
    # instances with DIFFERENT codehash but the same factory → collapsed by factory
    fac = "0x" + "fa" * 20
    nodes = []
    factory_of = {}
    for i in range(6):
        addr = "0x" + f"{i:040x}"
        nodes.append(ContractNode(address=addr, chain_id=1, codehash="0x" + f"{i:064x}",
                                  node_type=NodeType.VAULT, is_scope=False))   # different codehash
        factory_of[addr] = fac
    kept, classes = collapse_clones(nodes, cap=3, min_group=4, factory_of=factory_of)
    assert len(classes) == 1
    assert classes[0].total_count == 6 and classes[0].capped is True
    assert classes[0].class_id.startswith("fac:1:")
