"""
Clone collapsing — pure core (no I/O).

Guard against combinatorial explosion: thousands of identical contracts (e.g. Uniswap pairs)
must not bloat the graph — they collapse into a single `CloneClass` with a registration
pattern, a few examples, and a `capped` flag.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import CloneClass, ContractNode, NodeType, ProxyKind

DEFAULT_CLONE_CAP = 50          # how many examples we keep per class at most
DEFAULT_MIN_GROUP = 4           # group size at which a set of identical contracts counts as "repetitive"


def _group_key(node: ContractNode, factory_of: dict[str, str]) -> str | None:
    """
    Collapse key by LOGICAL identity (per-network; cross-chain mirrors are not collapsed):
      1) factory-created instance → by (factory + type): catches distinct-config instances
         (MetaMorpho vaults with differing codehash due to immutables);
      2) beacon proxy → by beacon (EtherFiNode clones on a shared beacon impl);
      3) EIP-1167 minimal proxy → by implementation;
      4) otherwise → by codehash (identical bytecode).
    None → does not participate.
    """
    if node.node_type == NodeType.CLONE_CLASS:
        return None
    fac = factory_of.get(node.address)
    if fac:
        return f"fac:{node.chain_id}:{fac}:{node.node_type.value}"
    if node.beacon:
        return f"beacon:{node.chain_id}:{node.beacon}"
    if node.implementation and node.proxy_kind == ProxyKind.EIP1167_MINIMAL:
        return f"impl:{node.chain_id}:{node.implementation}"
    if node.codehash:
        return f"code:{node.chain_id}:{node.codehash}"
    return None


def collapse_clones(
    nodes: Iterable[ContractNode],
    *,
    cap: int = DEFAULT_CLONE_CAP,
    min_group: int = DEFAULT_MIN_GROUP,
    factory_of: dict[str, str] | None = None,       # addr -> factory
    registration_of: dict[str, str] | None = None,  # group_key -> "factory.createPair -> PairCreated"
) -> tuple[list[ContractNode], list[CloneClass]]:
    """
    Split nodes into:
      - kept:    nodes that stay individual (unique ones + up to `cap` examples of each group);
      - classes: collapsed classes for large repeated groups.

    An in-scope node (`is_scope=True`) is never collapsed — seed addresses matter by name.
    """
    factory_of = factory_of or {}
    registration_of = registration_of or {}

    groups: dict[str, list[ContractNode]] = defaultdict(list)
    kept: list[ContractNode] = []

    for n in nodes:
        key = _group_key(n, factory_of)
        if key is None or n.is_scope:
            kept.append(n)
            continue
        groups[key].append(n)

    classes: list[CloneClass] = []
    for key, members in groups.items():
        if len(members) < min_group:
            # small group — keep by name
            kept.extend(members)
            continue

        members_sorted = sorted(members, key=lambda x: x.address)
        sample = members_sorted[:cap]
        # keep the first cap examples as real nodes (so they can be inspected)
        kept.extend(sample)

        factories = {factory_of.get(m.address) for m in members if factory_of.get(m.address)}
        factory = next(iter(factories), None) if len(factories) == 1 else None

        classes.append(
            CloneClass(
                class_id=key,
                codehash=members[0].codehash if key.startswith("code:") else None,
                implementation=members[0].implementation if key.startswith("impl:") else None,
                factory=factory,
                registration=registration_of.get(key, ""),
                total_count=len(members),
                sampled=[m.address for m in sample],
                capped=len(members) > cap,
            )
        )

    return kept, classes
