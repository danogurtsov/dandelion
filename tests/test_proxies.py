"""Proxy-detection unit tests — no network (read_slot is injected)."""
from dandelion.domain.models import ProxyKind, norm_addr
from dandelion.domain.proxies import (
    SLOT_1822,
    SLOT_1967_ADMIN,
    SLOT_1967_BEACON,
    SLOT_1967_IMPL,
    detect_proxy,
    parse_minimal_proxy,
)

IMPL = "0x" + "11" * 20
ADMIN = "0x" + "22" * 20
BEACON = "0x" + "33" * 20


def _word(addr: str) -> str:
    """32-byte word with the address in the low 20 bytes."""
    return "0x" + "0" * 24 + addr[2:]


def _reader(slots: dict[str, str]):
    def read(slot: str) -> str | None:
        return slots.get(slot.lower())
    return read


def test_eip1967_transparent():
    r = detect_proxy(None, _reader({
        SLOT_1967_IMPL: _word(IMPL),
        SLOT_1967_ADMIN: _word(ADMIN),
    }))
    assert r.kind == ProxyKind.EIP1967_TRANSPARENT
    assert r.implementation == norm_addr(IMPL)
    assert r.admin == norm_addr(ADMIN)


def test_eip1967_uups_no_admin():
    r = detect_proxy(None, _reader({SLOT_1967_IMPL: _word(IMPL)}))
    assert r.kind == ProxyKind.EIP1967_UUPS
    assert r.implementation == norm_addr(IMPL)
    assert r.admin is None


def test_beacon():
    r = detect_proxy(None, _reader({SLOT_1967_BEACON: _word(BEACON)}))
    assert r.kind == ProxyKind.BEACON
    assert r.beacon == norm_addr(BEACON)


def test_eip1822():
    r = detect_proxy(None, _reader({SLOT_1822: _word(IMPL)}))
    assert r.kind == ProxyKind.EIP1822
    assert r.implementation == norm_addr(IMPL)


def test_minimal_proxy_bytecode():
    code = "0x363d3d373d3d3d363d73" + IMPL[2:] + "5af43d82803e903d91602b57fd5bf3"
    assert parse_minimal_proxy(code) == norm_addr(IMPL)
    r = detect_proxy(code, _reader({}))
    assert r.kind == ProxyKind.EIP1167_MINIMAL
    assert r.implementation == norm_addr(IMPL)


def test_not_a_proxy():
    r = detect_proxy("0x6080604052", _reader({}))
    assert r.kind == ProxyKind.NONE


def test_zos_legacy_slot():
    from dandelion.domain.proxies import SLOT_ZOS
    r = detect_proxy(None, _reader({SLOT_ZOS: _word(IMPL)}))
    assert r.kind == ProxyKind.CUSTOM
    assert r.implementation == norm_addr(IMPL)
