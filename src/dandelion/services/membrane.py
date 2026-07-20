"""
Validation membrane — the only path through which AI-proposed actions may touch the graph.

The LLM proposes typed Actions; here each is EXECUTED deterministically and every result is
validated (strict address decode, target has code, not zero, not known-external) before an edge
is added. The membrane is SUPERSET-ONLY: it adds `origin="llm"` edges and returns discovered
address leads (for deterministic merge-expansion) — it never deletes or reclassifies anything
deterministic. A rejected action wastes a read and is counted in diagnostics; it cannot corrupt
the graph. This generalizes the proven `apply_llm_probes` pattern into a first-class chokepoint.
"""
from __future__ import annotations

from collections.abc import Callable

from ..domain.actions import Action
from ..domain.labels import is_known_external
from ..domain.models import ArchitectureGraph, EdgeType, is_zero, node_key
from ..domain.reads import decode_address_array, decode_address_strict
from .probes import enumerate_address_index, read_raw, reserve_components

# per-purpose edge label so AI leads inherit the same purpose-aware membership discipline
_LABEL = {"struct": "getter:struct", "asset": "getter:asset", "generic": "getter"}


def _reserves_of(graph: ArchitectureGraph, key: str) -> list[str]:
    """Addresses already discovered as this node's reserve list (getter:asset targets)."""
    out: list[str] = []
    for e in graph.edges:
        if e.src == key and e.edge_type == EdgeType.DEPENDS_ON and "getter:asset" in e.label:
            a = e.dst.split(":", 1)[1]
            if a not in out:
                out.append(a)
    return out


async def _execute(graph: ArchitectureGraph, rpc, node, act: Action) -> list[str]:
    """Run the deterministic read primitive for the action; return candidate addresses."""
    chain, addr = node.chain_id, node.address
    if act.kind == "read_addr":
        val = await read_raw(rpc, chain, addr, act.sig)
        a = decode_address_strict(val) if val else None
        return [a] if a else []
    if act.kind == "read_addr_array":
        val = await read_raw(rpc, chain, addr, act.sig)
        return decode_address_array(val, cap=act.cap) if val else []
    if act.kind == "enumerate_index":
        return await enumerate_address_index(rpc, chain, addr, act.name, cap=act.cap)
    if act.kind == "reserve_keyed":
        reserves = _reserves_of(graph, act.key)
        return await reserve_components(rpc, chain, addr, act.name, reserves) if reserves else []
    return []


async def apply_actions(
    graph: ArchitectureGraph,
    rpc,
    actions: list[Action],
    *,
    diag=None,
    on_event: Callable[[str, dict], None] | None = None,
) -> list[tuple[int, str]]:
    """
    Execute + validate AI actions. Adds origin='llm' edges for accepted leads and returns the
    newly-discovered (chain, addr) pairs for deterministic merge-expansion. Superset-only.
    """
    discovered: list[tuple[int, str]] = []
    for act in actions:
        node = graph.nodes.get(act.key)
        if node is None:
            if diag:
                diag.note("llm_rejected", act.key, "unknown node key")
            continue
        try:
            candidates = await _execute(graph, rpc, node, act)
        except Exception as e:  # noqa: BLE001
            candidates = []
            if diag:
                diag.note("llm_rejected", act.key, f"{act.kind} raised: {e}")
        label = f"llm:{act.kind} {act.sig}"
        for a in candidates:
            # validation gates — anything failing is dropped (never enters the graph)
            if not a or is_zero(a) or is_known_external(a):
                if diag:
                    diag.note("llm_rejected", act.key, f"{act.sig} -> filtered {a}")
                continue
            try:
                code = await rpc.get_code(node.chain_id, a)
            except Exception:  # noqa: BLE001
                code = "0x"
            if not code or code == "0x":            # must be a contract (not EOA/dead)
                if diag:
                    diag.note("llm_rejected", act.key, f"{act.sig} -> no code {a}")
                continue
            purpose_label = _LABEL.get(act.purpose, "getter")
            graph.add_edge(act.key, node_key(node.chain_id, a), EdgeType.DEPENDS_ON,
                           f"{purpose_label} {label}", origin="llm")
            if not graph.has_node(node.chain_id, a):
                discovered.append((node.chain_id, a))
            if on_event:
                on_event("llm_action", {"key": act.key, "kind": act.kind, "sig": act.sig, "found": a})
    return discovered
