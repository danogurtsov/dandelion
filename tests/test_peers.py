"""
Test #7 peer-config: LZ EID↔chain mapping + peers(eid)/trustedRemote decoders.
"""
from dandelion.domain.peers import (
    decode_peer_bytes32,
    decode_trusted_remote,
    eid_to_chain,
    known_lz_v1_chainids,
    known_lz_v2_eids,
    v1_chainid_to_chain,
)


def test_eid_maps_to_known_chains():
    assert eid_to_chain(30101) == 1        # ethereum
    assert eid_to_chain(30110) == 42161    # arbitrum
    assert eid_to_chain(30184) == 8453     # base
    assert eid_to_chain(99999) is None     # unknown EID → skip


def test_v1_chainid_maps():
    assert v1_chainid_to_chain(101) == 1
    assert v1_chainid_to_chain(110) == 42161
    assert v1_chainid_to_chain(999) is None


def test_known_lists_nonempty_and_consistent():
    assert set(known_lz_v2_eids()) >= {30101, 30110, 30111, 30184}
    assert set(known_lz_v1_chainids()) >= {101, 110, 111, 184}


def test_decode_peer_bytes32():
    addr = "aa" * 20
    word = "0x" + "0" * 24 + addr        # left-padded bytes32
    assert decode_peer_bytes32(word) == "0x" + addr
    assert decode_peer_bytes32("0x" + "0" * 64) is None   # zero → None
    assert decode_peer_bytes32(None) is None


def test_decode_trusted_remote_packed():
    remote = "bb" * 20
    local = "cc" * 20
    packed = remote + local              # abi.encodePacked(remote, local) = 40 bytes
    # ABI-return bytes: offset(0x20) + length(40=0x28) + data(padded)
    data = "0x" + f"{32:064x}" + f"{40:064x}" + packed.ljust(128, "0")
    assert decode_trusted_remote(data) == "0x" + remote


def test_decode_trusted_remote_empty():
    assert decode_trusted_remote(None) is None
    assert decode_trusted_remote("0x") is None
    # length=0 → no remote address
    empty = "0x" + f"{32:064x}" + f"{0:064x}"
    assert decode_trusted_remote(empty) is None
