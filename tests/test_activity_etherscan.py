"""Tests for the Etherscan deployer lookup (getcontractcreation) + CompositeActivity fallback."""
import asyncio

from dandelion.adapters.activity.composite import CompositeActivity
from dandelion.adapters.activity.etherscan import EtherscanActivity, parse_creations
from dandelion.ports import ActivitySummary


def test_parse_creations():
    res = [
        {"contractAddress": "0x" + "Aa" * 20, "contractCreator": "0x" + "bb" * 20, "txHash": "0x1"},
        {"contractAddress": "0x" + "Cc" * 20, "contractCreator": "0x" + "dd" * 20, "txHash": "0x2"},
    ]
    got = parse_creations(res)
    assert got["0x" + "aa" * 20] == "0x" + "bb" * 20
    assert got["0x" + "cc" * 20] == "0x" + "dd" * 20


def test_etherscan_deployer_no_key():
    # without a key, returns None gracefully with no network calls
    a = EtherscanActivity(api_key=None)
    a.api_key = None
    assert asyncio.run(a.deployer(1, "0x" + "aa" * 20)) is None


class _BS:
    """Blockscout stub: has top_callers but NO deployer."""
    async def summary(self, chain, addr):
        return ActivitySummary(is_contract=True, top_callers=[("0x" + "11" * 20, 5)])

    async def deployer(self, chain, addr):
        return None

    async def deployments_by(self, chain, deployer, *, cap=40):
        return []


class _ES:
    """Etherscan stub: returns only the deployer."""
    async def summary(self, chain, addr):
        return ActivitySummary(is_contract=True, deployer="0x" + "de" * 20)

    async def deployer(self, chain, addr):
        return "0x" + "de" * 20


def test_composite_fills_deployer_from_second():
    comp = CompositeActivity(providers=[_BS(), _ES()])
    s = asyncio.run(comp.summary(1, "0x" + "aa" * 20))
    assert s.top_callers == [("0x" + "11" * 20, 5)]   # from Blockscout
    assert s.deployer == "0x" + "de" * 20              # filled in from Etherscan


def test_composite_deployer_fallback():
    comp = CompositeActivity(providers=[_BS(), _ES()])
    assert asyncio.run(comp.deployer(1, "0x" + "aa" * 20)) == "0x" + "de" * 20
