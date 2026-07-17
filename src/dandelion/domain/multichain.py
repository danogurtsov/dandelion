"""
Cross-chain mirror detection — pure core.

Many protocols deploy deterministically → the same address on many chains.
We confirm a mirror by comparing codehash (to rule out an accidental address match).
"""
from __future__ import annotations


def is_mirror(codehash_seed: str | None, codehash_other: str | None) -> bool:
    """Same address on another chain is a mirror only if the codehash matches."""
    if not codehash_seed or not codehash_other:
        return False
    return codehash_seed.lower() == codehash_other.lower()


def detect_mirrors(
    codehash_seed: str | None,
    per_chain_codehash: dict[int, str | None],
) -> list[int]:
    """
    per_chain_codehash — {chain_id: codehash|None} for the SAME address on different chains.
    Returns the chains where the codehash matched the seed → confirmed mirrors.
    """
    return [c for c, h in per_chain_codehash.items() if is_mirror(codehash_seed, h)]
