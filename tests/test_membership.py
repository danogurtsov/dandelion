"""Membership v2 tests: authority closure, known-external, signal re-evaluation."""
from dandelion.domain.labels import is_known_external
from dandelion.domain.membership import classify, membership_score
from dandelion.domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    Role,
    node_key,
)
from dandelion.services.reconstruct import finalize_membership

ADMIN = "0x" + "a" * 40
SEED = "0x" + "1" * 40
PROJ = "0x" + "2" * 40   # controlled by the same ADMIN → member
DEP = "0x" + "3" * 40    # references seed, but foreign authority → external dependency
CHAINLINK_OWNER = "0x" + "9" * 40


def test_weak_signal_alone_is_candidate_not_member():
    # a reference alone (explicit_reference) is not enough for member
    assert classify(membership_score({"explicit_reference"})) == "candidate"
    assert classify(membership_score({"cooccurrence"})) == "candidate"
    # shared control → member
    assert classify(membership_score({"shared_admin"})) == "member"
    assert classify(membership_score({"is_proxy_or_impl"})) == "member"


def test_known_external_labels():
    assert is_known_external("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")  # WETH
    assert is_known_external("0x000000000022D473030F116dDEE9F6B43aC78BA3")  # Permit2
    assert not is_known_external(SEED)


def test_authority_closure_shared_admin_makes_member():
    g = ArchitectureGraph()
    seed = ContractNode(address=SEED, chain_id=1, is_scope=True, admin=ADMIN)
    g.add_node(seed)
    # PROJ is controlled by the SAME ADMIN → shared_admin → member
    g.add_node(ContractNode(address=PROJ, chain_id=1, is_scope=False, admin=ADMIN))
    # DEP: seed references it, but authority is foreign → only explicit_reference → candidate/external
    g.add_node(ContractNode(address=DEP, chain_id=1, is_scope=False,
                            roles=[Role("owner", CHAINLINK_OWNER, "owner()")]))
    g.add_edge(node_key(1, SEED), node_key(1, DEP), EdgeType.DEPENDS_ON, "ref")

    finalize_membership(g)
    assert g.get_node(1, PROJ).membership == "member"      # shared control
    assert g.get_node(1, DEP).membership == "candidate"    # reference ≠ member (foreign authority)


def test_known_external_forced_external_even_if_referenced():
    g = ArchitectureGraph()
    weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    g.add_node(ContractNode(address=SEED, chain_id=1, is_scope=True, admin=ADMIN))
    g.add_node(ContractNode(address=weth, chain_id=1, is_scope=False))
    g.add_edge(node_key(1, SEED), node_key(1, weth), EdgeType.DEPENDS_ON, "holds WETH")
    finalize_membership(g)
    assert g.get_node(1, weth).membership == "external"     # known infra, despite the reference


def test_deployer_closure_anchors_cluster():
    g = ArchitectureGraph()
    dep = "0x" + "7" * 40   # project deployer (not public)
    g.add_node(ContractNode(address=SEED, chain_id=1, is_scope=True, deployer=dep))
    g.add_node(ContractNode(address=PROJ, chain_id=1, is_scope=False, deployer=dep))       # same → member
    g.add_node(ContractNode(address=DEP, chain_id=1, is_scope=False, deployer="0x" + "8" * 40))  # foreign → external
    finalize_membership(g)
    assert g.get_node(1, PROJ).membership == "member"
    assert g.get_node(1, DEP).membership == "external"


def test_address_getters_extraction():
    from dandelion.domain.abi import address_getters
    abi = [
        {"type": "function", "name": "getPool", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},
        {"type": "function", "name": "ADDRESSES_PROVIDER", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},
        {"type": "function", "name": "getReserveData", "stateMutability": "view",
         "inputs": [{"type": "address"}], "outputs": [{"type": "address"}]},   # has an argument → no
        {"type": "function", "name": "totalSupply", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "uint256"}]},                        # not address → no
    ]
    g = address_getters(abi)
    assert g == ["getPool()", "ADDRESSES_PROVIDER()"]
    assert address_getters(None) == []


def test_address_array_decode_and_getters():
    from dandelion.domain.abi import address_array_getters
    from dandelion.domain.reads import decode_address_array
    a1 = "ab" * 20
    a2 = "cd" * 20
    data = ("0x" + "0"*62 + "20"          # offset = 32
            + "0"*63 + "2"                 # length = 2
            + "0"*24 + a1 + "0"*24 + a2)
    got = decode_address_array(data)
    assert got == ["0x" + a1, "0x" + a2]
    abi = [{"type": "function", "name": "getReservesList", "stateMutability": "view",
            "inputs": [], "outputs": [{"type": "address[]"}]}]
    assert address_array_getters(abi) == ["getReservesList()"]


def test_indexed_address_getters():
    from dandelion.domain.abi import indexed_address_getters
    abi = [
        {"type": "function", "name": "getToken", "stateMutability": "view",
         "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
        {"type": "function", "name": "allPairs", "stateMutability": "view",
         "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
        {"type": "function", "name": "owner", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},                  # no-arg → no
    ]
    assert indexed_address_getters(abi) == ["getToken", "allPairs"]


def test_created_addresses_from_logs():
    from dandelion.domain.factory_events import created_addresses_from_logs
    inst1 = "0x" + "0" * 24 + "11" * 20
    inst2 = "0x" + "0" * 24 + "22" * 20
    token = "0x" + "0" * 24 + "aa" * 20   # recurs → not an instance
    topic0 = "0x" + "de" * 32
    logs = [
        {"topics": [topic0, inst1, token], "data": "0x"},   # instance1 + shared token
        {"topics": [topic0, inst2, token], "data": "0x"},   # instance2 + same token
    ]
    got = set(created_addresses_from_logs(logs))
    assert got == {"0x" + "11" * 20, "0x" + "22" * 20}       # token filtered out (recurs)
