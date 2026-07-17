"""
LLM reasoning/enrichment pass — a semantic layer over the deterministic graph.

Takes the reconstructed ArchitectureGraph and produces: (1) what the protocol is and
how it is split across chains, (2) semantic roles for nodes (especially unknown ones),
(3) suggested probes (what to read next — feeds the next turn of the loop). The LLM does
NOT invent addresses — it only works with nodes already in the graph. Compact/parse are
pure (testable without the network).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from ..domain.models import ArchitectureGraph
from ..ports import LlmMessage

_SYSTEM = (
    "You are an on-chain protocol architecture analyst. You are given a graph reconstructed "
    "from live chain state: nodes are contracts (address, name, type, roles, proxy/impl), edges "
    "are relations. Produce a concise semantic understanding. Never invent addresses — only use "
    "node keys present in the input. Return ONLY a JSON object, no prose."
)

_INSTRUCT = (
    'Return JSON: {"protocol": "<1-2 sentences: what this protocol is and how it is split across '
    'chains>", "labels": [{"key": "<node key from input>", "role": "<short purpose, e.g. lending '
    'pool / price oracle / admin multisig>"}], "probes": [{"key": "<node key>", '
    '"read": "<exactly ONE no-arg view function signature, e.g. getMinDelay(); no alternatives, '
    'no arguments>", "why": "<what it would confirm>"}]}. '
    "Only add labels where you contribute real signal (esp. type=unknown). Keep it short."
)


def compact_graph(graph: ArchitectureGraph, *, max_nodes: int = 60) -> str:
    """Compact textual representation of the graph for the prompt (no raw code)."""
    lines = [f"chains: {graph.chains}", "nodes:"]
    for i, n in enumerate(graph.nodes.values()):
        if i >= max_nodes:
            lines.append(f"  … (+{len(graph.nodes) - max_nodes} more nodes)")
            break
        roles = ",".join(f"{r.name}={r.holder[:10]}" for r in n.roles if r.holder)
        parts = [n.key, f"({n.name})" if n.name else "", f"type={n.node_type.value}"]
        if n.proxy_kind.value != "none":
            parts.append(f"proxy={n.proxy_kind.value}")
        if n.implementation:
            parts.append(f"impl={n.implementation[:10]}")
        if roles:
            parts.append(f"roles=[{roles}]")
        if n.membership != "member":
            parts.append(f"membership={n.membership}")
        # meaningful state + results of prior probes (so the LLM sees them next round)
        st = {kk: vv for kk, vv in n.state.items() if kk not in ("top_callers", "sample_txs")}
        if st:
            parts.append("state={" + ", ".join(f"{kk}={str(vv)[:24]}" for kk, vv in st.items()) + "}")
        lines.append("  " + " ".join(p for p in parts if p))
    lines.append("edges:")
    for e in graph.edges[:80]:
        lines.append(f"  {e.src} -{e.edge_type.value}-> {e.dst}")
    return "\n".join(lines)


def parse_llm_json(text: str) -> dict:
    """Extract JSON from the LLM response (strip ``` fences, take the first {...})."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return {}


async def apply_llm_probes(
    graph: ArchitectureGraph,
    rpc,
    probes: list[dict],
    *,
    on_event: Callable[[str, dict], None] | None = None,
) -> list[tuple[int, str]]:
    """
    Close the loop: apply the LLM's suggested probes (no-arg getters) deterministically
    and record the result in node.state[sig]. If a probe returns an ADDRESS, that's a lead
    on a new entity: add a DEPENDS_ON edge and return it (for the next round).
    Returns a list of (chain, addr) newly discovered addresses.
    """
    from ..domain.models import EdgeType, is_zero, node_key
    from ..domain.reads import decode_address_strict
    from .probes import read_raw

    discovered: list[tuple[int, str]] = []
    for pr in probes or []:
        node = graph.nodes.get(pr.get("key", ""))
        m = re.search(r"([A-Za-z_]\w*\(\))", pr.get("read") or "")
        if not node or not m:
            continue
        sig = m.group(1)
        val = await read_raw(rpc, node.chain_id, node.address, sig)
        if val is None:
            continue
        node.state[sig] = val
        if on_event:
            on_event("probe", {"key": node.key, "read": sig, "value": val[:20]})
        a = decode_address_strict(val)
        if a and not is_zero(a) and not graph.has_node(node.chain_id, a):
            graph.add_edge(node.key, node_key(node.chain_id, a), EdgeType.DEPENDS_ON, f"via {sig}")
            discovered.append((node.chain_id, a))
    return discovered


async def enrich_graph(
    graph: ArchitectureGraph,
    llm,
    *,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict:
    """Enrich the graph with semantics via the LLM. Returns the parsed response."""
    ctx = compact_graph(graph)
    messages = [
        LlmMessage("user", f"{_SYSTEM}\n\n{ctx}\n\n{_INSTRUCT}"),
    ]
    raw = await llm.complete(messages, max_tokens=1500)
    data = parse_llm_json(raw)

    if data.get("protocol"):
        graph.meta["protocol"] = data["protocol"]
    for lab in data.get("labels", []):
        node = graph.nodes.get(lab.get("key", ""))
        if node and lab.get("role"):
            node.notes.append(f"llm-role: {lab['role']}")
    if data.get("probes"):
        graph.meta["llm_probes"] = data["probes"]
    if on_event:
        on_event("enrich", {"protocol": data.get("protocol"),
                            "labels": len(data.get("labels", [])),
                            "probes": len(data.get("probes", []))})
    return data


async def reason_loop(
    graph: ArchitectureGraph,
    rpc,
    llm,
    *,
    source: object | None = None,
    rounds: int = 2,
    on_event: Callable[[str, dict], None] | None = None,
) -> ArchitectureGraph:
    """
    Full determinism↔LLM loop until convergence: the LLM looks at the graph (+ results of
    prior probes) → suggests probes → we apply them; address results → we merge-expand the
    graph deterministically → back to the LLM. Stop: no new addresses or rounds exhausted.
    """
    from .reconstruct import reconstruct

    for r in range(rounds):
        data = await enrich_graph(graph, llm, on_event=on_event)
        discovered = await apply_llm_probes(graph, rpc, data.get("probes", []), on_event=on_event)
        if on_event:
            on_event("reason_round", {"round": r + 1, "discovered": len(discovered)})
        if not discovered:
            break
        await reconstruct(discovered, rpc, source=source, existing=graph,
                          probe_chains=[], on_event=on_event)
    return graph
