"""
Chain registry + dRPC URL builder.

dRPC multichain: one key, network slug in the path — https://lb.drpc.live/<slug>/<key>.
Secrets (the key) are NOT hardcoded here — they come from env/config.
"""
from __future__ import annotations

# chain_id -> (human name, dRPC network slug)
CHAINS: dict[int, tuple[str, str]] = {
    1: ("ethereum", "ethereum"),
    10: ("optimism", "optimism"),
    56: ("bsc", "bsc"),
    100: ("gnosis", "gnosis"),
    137: ("polygon", "polygon"),
    146: ("sonic", "sonic"),
    8453: ("base", "base"),
    42161: ("arbitrum", "arbitrum"),
    43114: ("avalanche", "avalanche"),
    59144: ("linea", "linea"),
    534352: ("scroll", "scroll"),
}

DEFAULT_PROBE_CHAINS = [1, 42161, 10, 8453, 137, 56, 43114]

DRPC_BASE = "https://lb.drpc.live"


def chain_name(chain_id: int) -> str:
    return CHAINS.get(chain_id, (str(chain_id), ""))[0]


def drpc_urls(key: str, chains: list[int] | None = None, base: str = DRPC_BASE) -> dict[int, str]:
    """Build a {chain_id: url} map for dRPC from a single key."""
    chains = chains or list(CHAINS)
    return {c: f"{base}/{CHAINS[c][1]}/{key}" for c in chains if c in CHAINS}
