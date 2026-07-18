"""
LLM ablation: quantify what the reasoning loop adds over pure determinism.

For each fixture: reconstruct deterministically (base), then run the reason loop (enrich) and
measure the delta — nodes discovered, names/labels added, members found, and how many of the
LLM's proposed probes actually resolved to an address. Report the numbers as they are; the
honest expectation is that the LLM adds little on registry-friendly protocols and more on
opaque ones (dummy-impl dispatchers, bytecode-only).

Usage:
  DRPC_KEY=... CLAUDE_CODE_OAUTH_TOKEN=... PYTHONPATH=src \
    python evals/ablation.py [--llm anthropic:claude-sonnet-5] [--slugs fluid,aave-pool]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dandelion.adapters.llm.factory import build_llm  # noqa: E402
from dandelion.adapters.rpc.jsonrpc import JsonRpcClient  # noqa: E402
from dandelion.adapters.sources.ladder import default_ladder  # noqa: E402
from dandelion.chains import drpc_urls  # noqa: E402
from dandelion.services.enrich import reason_loop  # noqa: E402
from dandelion.services.reconstruct import reconstruct  # noqa: E402

GOLDEN = Path(__file__).parent / "golden" / "debug_set.json"


def _snap(g) -> dict:
    return {
        "nodes": len(g.nodes),
        "named": sum(1 for n in g.nodes.values() if n.name),
        "members": sum(1 for n in g.nodes.values() if n.membership == "member"),
        "llm_labels": sum(1 for n in g.nodes.values()
                          for note in n.notes if note.startswith("llm-role:")),
    }


async def ablate(case: dict, key: str, llm_spec: str) -> dict:
    chains = sorted({c for c, _ in case["seeds"]} | set(case.get("probe_chains", [])))
    rpc = JsonRpcClient(rpc_urls=drpc_urls(key, chains))
    seeds = [(c, a) for c, a in case["seeds"]]
    ladder = default_ladder(etherscan_key=os.getenv("ETHERSCAN_API_KEY"))

    graph = await reconstruct(seeds, rpc, max_nodes=40,
                              probe_chains=case.get("probe_chains", [seeds[0][0]]), source=ladder)
    base = _snap(graph)

    events: list[tuple[str, dict]] = []
    llm = build_llm(llm_spec)
    await reason_loop(graph, rpc, llm, source=ladder, rounds=2,
                      on_event=lambda k, d: events.append((k, d)))
    after = _snap(graph)

    proposed = sum(d.get("probes", 0) for k, d in events if k == "enrich")   # already a count
    resolved = sum(d.get("discovered", 0) for k, d in events if k == "reason_round")
    return {
        "slug": case["slug"], "base": base, "after": after,
        "delta_nodes": after["nodes"] - base["nodes"],
        "delta_named": after["named"] - base["named"],
        "delta_members": after["members"] - base["members"],
        "llm_labels": after["llm_labels"],
        "probes_proposed": proposed, "probes_resolved_to_address": resolved,
        "protocol_label": graph.meta.get("protocol", "")[:80],
    }


async def main() -> None:
    key = os.getenv("DRPC_KEY")
    if not key:
        print("set DRPC_KEY")
        sys.exit(2)
    llm_spec = "anthropic:claude-sonnet-5"
    slugs = None
    if "--llm" in sys.argv:
        llm_spec = sys.argv[sys.argv.index("--llm") + 1]
    if "--slugs" in sys.argv:
        slugs = set(sys.argv[sys.argv.index("--slugs") + 1].split(","))

    cases = [c for c in json.loads(GOLDEN.read_text()) if not slugs or c["slug"] in slugs]
    print(f"llm: {llm_spec}\n")
    print(f"{'slug':18s} {'nodes b→a':12s} {'named b→a':12s} {'probes p/resolved':18s} labels")
    for case in cases:
        try:
            r = await ablate(case, key, llm_spec)
        except Exception as e:  # noqa: BLE001
            print(f"{case['slug']:18s} ERR {type(e).__name__}: {e}")
            continue
        b, a = r["base"], r["after"]
        print(f"{r['slug']:18s} {b['nodes']:>3}→{a['nodes']:<8} {b['named']:>3}→{a['named']:<8} "
              f"{r['probes_proposed']:>2}/{r['probes_resolved_to_address']:<15} {r['llm_labels']}")
        if r["protocol_label"]:
            print(f"    llm: {r['protocol_label']}")


if __name__ == "__main__":
    asyncio.run(main())
