# evals

Live evaluation of the reconstruction against a golden set of real protocols.

- `golden/debug_set.json` — curated cases: seed addresses + `probe_chains` + expectations
  (proxy kind, implementation, cross-chain mirrors, node counts).
- `metrics.py` — compares a reconstructed `ArchitectureGraph` to the expectations.
- `run_evals.py` — runs `reconstruct` for each case over live RPC and reports pass/fail + metrics.

## Run

```bash
DRPC_KEY=<your dRPC key> PYTHONPATH=src python evals/run_evals.py [--dump]
```

`--dump` writes each reconstructed graph and a summary to `evals/report/` (git-ignored).
The RPC key is read from the environment; it is never stored in the repo.

Cases span the hard shapes on purpose: a simple proxy, a factory, a cross-chain
bridge (same address on several chains), immutable protocols (negative controls),
and role-heavy deployments.
