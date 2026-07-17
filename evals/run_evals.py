"""
Eval runner: run reconstruct on golden fixtures via dRPC + metrics.

Usage:
  DRPC_KEY=... PYTHONPATH=src python evals/run_evals.py [--dump]

The dRPC key comes from the DRPC_KEY env var (not hardcoded). Reports go to evals/report/ (gitignored).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metrics import evaluate, is_pass  # noqa: E402

from dandelion.adapters.rpc.jsonrpc import JsonRpcClient  # noqa: E402
from dandelion.adapters.sources.ladder import default_ladder  # noqa: E402
from dandelion.chains import drpc_urls  # noqa: E402
from dandelion.services.reconstruct import reconstruct  # noqa: E402

GOLDEN = Path(__file__).parent / "golden" / "debug_set.json"
REPORT_DIR = Path(__file__).parent / "report"


async def run_case(case: dict, key: str, dump: bool) -> dict:
    chains = sorted({c for c, _ in case["seeds"]} | set(case.get("probe_chains", [])))
    client = JsonRpcClient(rpc_urls=drpc_urls(key, chains))
    seeds = [(c, a) for c, a in case["seeds"]]
    t0 = time.monotonic()
    graph = await reconstruct(
        seeds, client, max_nodes=40, probe_chains=case.get("probe_chains", [seeds[0][0]]),
        source=default_ladder(etherscan_key=os.getenv("ETHERSCAN_API_KEY")),
    )
    dt = round(time.monotonic() - t0, 1)
    checks = evaluate(graph, case["seeds"], case.get("expect", {}))
    result = {"slug": case["slug"], "seconds": dt, "pass": is_pass(checks), "checks": checks}
    if dump:
        REPORT_DIR.mkdir(exist_ok=True)
        (REPORT_DIR / f"{case['slug']}.graph.json").write_text(graph.to_json())
    return result


async def main() -> None:
    key = os.getenv("DRPC_KEY")
    if not key:
        print("set DRPC_KEY env")
        sys.exit(2)
    dump = "--dump" in sys.argv
    cases = json.loads(GOLDEN.read_text())
    results = []
    for case in cases:
        try:
            results.append(await run_case(case, key, dump))
        except Exception as e:  # noqa: BLE001
            results.append({"slug": case["slug"], "pass": False, "error": f"{type(e).__name__}: {e}"})

    print(f"\n{'slug':18s} {'pass':5s} {'sec':4s}  checks")
    npass = 0
    for r in results:
        npass += 1 if r.get("pass") else 0
        if "error" in r:
            print(f"{r['slug']:18s} ERR        {r['error'][:60]}")
            continue
        c = r["checks"]
        brief = " ".join(f"{k}={v}" for k, v in c.items()
                          if k in ("seed_proxy", "named_nodes", "unknown_nodes", "mirror_coverage", "clone_classes"))
        print(f"{r['slug']:18s} {'✓' if r['pass'] else '✗':5s} {r.get('seconds',0):<4} {brief}")
    print(f"\n{npass}/{len(results)} passed")
    if dump:
        REPORT_DIR.mkdir(exist_ok=True)
        (REPORT_DIR / "summary.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
