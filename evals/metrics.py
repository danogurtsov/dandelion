"""Eval metrics: compare the reconstructed graph against golden expectations."""
from __future__ import annotations

from dandelion.domain.models import ArchitectureGraph, node_key, norm_addr


def evaluate(graph: ArchitectureGraph, seeds: list, expect: dict) -> dict:
    """Return {check: pass/fail/value} for a single fixture."""
    chain, addr = seeds[0]
    seed = graph.get_node(chain, addr)
    checks: dict[str, object] = {}

    checks["seed_found"] = seed is not None
    if seed is None:
        return checks

    checks["seed_type"] = seed.node_type.value
    checks["seed_proxy"] = seed.proxy_kind.value

    if expect.get("is_proxy"):
        checks["is_proxy_ok"] = seed.proxy_kind.value != "none" and seed.implementation is not None
    if "proxy_kind" in expect:
        checks["proxy_kind_ok"] = seed.proxy_kind.value == expect["proxy_kind"]
    if "impl" in expect:
        checks["impl_ok"] = (seed.implementation == norm_addr(expect["impl"]))
    if "min_nodes" in expect:
        checks["nodes"] = len(graph.nodes)
        checks["min_nodes_ok"] = len(graph.nodes) >= expect["min_nodes"]

    if "mirror_chains" in expect:
        mirror_dst = {
            e.dst.split(":")[0]
            for e in graph.edges
            if e.edge_type.value == "mirrors_deployment" and e.src == node_key(chain, addr)
        }
        got = {int(c) for c in mirror_dst}
        want = set(expect["mirror_chains"])
        checks["mirror_coverage"] = f"{len(got & want)}/{len(want)}"
        checks["mirror_ok"] = got >= want

    if expect.get("no_false_clone_classes"):
        checks["clone_classes"] = len(graph.clone_classes)
        checks["no_false_clones_ok"] = len(graph.clone_classes) == 0

    # classification diagnostics: how many nodes remained unknown
    unknown = sum(1 for n in graph.nodes.values() if n.node_type.value == "unknown")
    checks["unknown_nodes"] = f"{unknown}/{len(graph.nodes)}"
    named = sum(1 for n in graph.nodes.values() if n.name)
    checks["named_nodes"] = f"{named}/{len(graph.nodes)}"
    m = sum(1 for n in graph.nodes.values() if n.membership == "member")
    c = sum(1 for n in graph.nodes.values() if n.membership == "candidate")
    ext = sum(1 for n in graph.nodes.values() if n.membership == "external")
    checks["membership"] = f"m{m}/c{c}/e{ext}"
    return checks


def is_pass(checks: dict) -> bool:
    return all(v for k, v in checks.items() if k.endswith("_ok"))
