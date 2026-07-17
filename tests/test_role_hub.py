"""
Test #6 role-hub: holders of ALL roles (ACLManager/Aave), RoleRevoked accounting, role names.
"""
import asyncio

from dandelion.services.probes import (
    DEFAULT_ADMIN_ROLE,
    ROLE_GRANTED_TOPIC,
    ROLE_REVOKED_TOPIC,
    is_admin_role,
    role_holders,
    role_name,
)

POOL_ADMIN = "0x12ad05bde78c5ab75238ce885307f96ecd482bb402ef831f99e7018a0f169b7b"
FLASH_BORROWER = "0x939b8dfb57ecef2aea54a93a15e86768b9d4089f1ba61c245e6ec980695f4ca4"


def _acct(b: str) -> str:
    return "0x" + "0" * 24 + b * 20   # topic-word with address b*20


def _addr(b: str) -> str:
    return "0x" + b * 20


def _grant(role: str, acct_byte: str) -> dict:
    return {"topics": [ROLE_GRANTED_TOPIC, role, _acct(acct_byte)], "data": "0x"}


def _revoke(role: str, acct_byte: str) -> dict:
    return {"topics": [ROLE_REVOKED_TOPIC, role, _acct(acct_byte)], "data": "0x"}


class RoleRpc:
    """Returns different logs for RoleGranted vs RoleRevoked (by topic0)."""
    def __init__(self, granted, revoked):
        self.granted, self.revoked = granted, revoked

    async def get_logs(self, chain, addr, topics=None, from_block=0, to_block="latest"):
        t0 = topics[0] if topics else None
        if t0 == ROLE_GRANTED_TOPIC:
            return self.granted
        if t0 == ROLE_REVOKED_TOPIC:
            return self.revoked
        return []


def test_role_name_known_and_unknown():
    assert role_name(DEFAULT_ADMIN_ROLE) == "DEFAULT_ADMIN_ROLE"
    assert role_name(POOL_ADMIN) == "POOL_ADMIN"
    assert role_name("0x" + "ff" * 32).startswith("role:0xffff")


def test_role_holders_all_roles():
    rpc = RoleRpc(
        granted=[_grant(DEFAULT_ADMIN_ROLE, "aa"), _grant(POOL_ADMIN, "bb")],
        revoked=[],
    )
    got = asyncio.run(role_holders(rpc, 1, _addr("01")))
    assert (DEFAULT_ADMIN_ROLE, _addr("aa")) in got
    assert (POOL_ADMIN, _addr("bb")) in got
    assert len(got) == 2   # not only DEFAULT_ADMIN — both roles


def test_role_holders_respects_revoke():
    rpc = RoleRpc(
        granted=[_grant(POOL_ADMIN, "aa"), _grant(POOL_ADMIN, "bb")],
        revoked=[_revoke(POOL_ADMIN, "aa")],   # aa stripped of the role → no authority
    )
    got = asyncio.run(role_holders(rpc, 1, _addr("01")))
    assert (POOL_ADMIN, _addr("bb")) in got
    assert (POOL_ADMIN, _addr("aa")) not in got


def test_is_admin_role_separates_operational():
    # admin roles = project authority
    assert is_admin_role(DEFAULT_ADMIN_ROLE)
    assert is_admin_role(POOL_ADMIN)
    # operational (flash-borrower whitelist) — NOT authority
    assert not is_admin_role(FLASH_BORROWER)
    assert not is_admin_role("0x" + "ff" * 32)


def test_role_holders_dedup():
    rpc = RoleRpc(granted=[_grant(POOL_ADMIN, "aa"), _grant(POOL_ADMIN, "aa")], revoked=[])
    got = asyncio.run(role_holders(rpc, 1, _addr("01")))
    assert got.count((POOL_ADMIN, _addr("aa"))) == 1
