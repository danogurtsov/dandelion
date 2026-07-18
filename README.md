<p align="center">
  <img src="assets/banner.jpeg" alt="dandelion" width="100%" />
</p>

<h1 align="center">dandelion</h1>

<p align="center">
  <strong>Reconstruct a protocol's on-chain architecture from addresses, not from a repository.</strong>
</p>

<p align="center">
  <a href="https://github.com/danogurtsov/dandelion/actions/workflows/ci.yml"><img src="https://github.com/danogurtsov/dandelion/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/Python-3.11--3.13-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white" alt="Ruff" />
  <img src="https://img.shields.io/badge/types-mypy-2A6DB2" alt="mypy" />
  <img src="https://img.shields.io/badge/tests-124%20passing-3fb950" alt="tests" />
  <img src="https://img.shields.io/badge/License-MIT-blue" alt="License: MIT" />
</p>

---

Researching a protocol usually starts from a GitHub repo. But often all you have is a set of
**addresses on a live chain**: a deployment, an unknown fork, a system you want to understand.
dandelion works straight from the chain. Give it a set of addresses and it resolves their code,
reads their **real state**, follows their links, classifies roles and money flow, measures how
the contracts are **actually used**, and emits one typed **architecture graph** you can build
your on-chain research on.

```
addresses + chain  ─▶  dandelion  ─▶  ArchitectureGraph (JSON)
                                        nodes · proxies↔impl · roles & authorities ·
                                        reserves & own tokens · clone-classes ·
                                        cross-chain mirrors & peers · activity
```

As one example, a single Aave v3 Pool address is enough for dandelion to crawl the whole
protocol on its own: the addresses provider, configurator, oracle, ACL manager, rewards and
treasury, plus every per-reserve aToken, debt token and rate strategy, folded into
clone-classes. No hints, no repo.

## Why on-chain-first

- **No repo required.** It finds the contract's source in any language, or decompiles the
  bytecode when there is none. Unverified forks are handled the same way.
- **Real state is part of the answer.** Who is admin *right now*, current parameters, where
  funds sit. Often the crux, and absent from source.
- **Real usage matters.** Recent transactions and traces separate live components from dead
  ones and reveal actual callers and admin actions.
- **Over-inclusive by design, but measured.** When a contract might belong to the project, it
  gets crawled. Growth is bounded by real structure (clone-collapse, a shallow external
  boundary), never by an arbitrary node cap. And over-inclusion is not a blind spot: every run
  reports a **membership precision proxy** and audits external-asset / operator-key leakage
  (`--audit`), so precision is a tracked number, not just recall.
- **Forensic-grade, no silent failures.** Pin every read to a historical block (`--block N`)
  to reconstruct the architecture as it was during an incident. Every skipped read is counted
  and surfaced in the graph's diagnostics, so an incomplete map declares itself instead of
  looking complete.

## Install

```bash
git clone https://github.com/danogurtsov/dandelion
cd dandelion
pip install -e ".[dev]"
```

## Usage

```bash
# Map a protocol from one or more seed addresses
dandelion map 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2 \
    --chain 1 --rpc https://eth.drpc.org --out aave.graph.json

# Force the Etherscan source step off (keyless: Sourcify + Blockscout only)
dandelion map 0xADDR --chain 1 --rpc $RPC --no-etherscan

# Add the LLM reasoning loop (propose reads, probe deterministically, expand)
dandelion map 0xADDR --chain 1 --rpc $RPC --enrich --llm anthropic:claude-sonnet-5

# Reconstruct the architecture as of a historical block (incident forensics)
dandelion map 0xADDR --chain 1 --rpc $ARCHIVE_RPC --block 17000000 --audit
```

Or from Python:

```python
import asyncio
from dandelion.adapters.rpc.jsonrpc import JsonRpcClient
from dandelion.adapters.sources.ladder import default_ladder
from dandelion.services.reconstruct import reconstruct

async def main():
    rpc = JsonRpcClient(rpc_urls={1: "https://eth.drpc.org"})
    graph = await reconstruct([(1, "0x8787...4E2")], rpc, source=default_ladder())
    print(graph.summary())
    graph.to_json()  # the machine-readable map your research builds on

asyncio.run(main())
```

## What you get: the architecture graph

- **nodes**: each contract with code, source tier, proxy kind, implementation, admin,
  codehash, type (token / pool / vault / router / factory / oracle / governance / timelock /
  multisig), roles, key state, and a **membership** verdict (member / candidate / external).
- **token roles**: every token is classified as `own` (project-issued: aTokens, debt tokens,
  governance / LP), `reserved` (assets the protocol custodies, i.e. the accepted deposit list),
  or `transient` (merely seen in flows).
- **edges**: `is_proxy_for`, `holds_role_over`, `depends_on`, `created_by`, `calls`,
  `mirrors_deployment` (cross-chain), `peer_of` (LayerZero).
- **clone_classes**: thousands of identical instances folded into one class (logic identity
  plus a sample cap), never crawled in full.
- **logical entities**: address-less market state (e.g. Morpho Blue markets) captured as
  hyperedges to their real dependencies.

## How it works

A deterministic and LLM loop, breadth-first, fully async:

1. **Resolve**: fetch code, detect the proxy pattern (EIP-1967 / 1822 / 1167 / beacon /
   diamond / ZeppelinOS), classify the type from bytecode selectors, and resolve name/ABI
   through a source ladder (**Etherscan V2 → Sourcify → Blockscout → Heimdall decompile**).
2. **Expand**: follow the project's own structure deterministically.
   - **getter expansion by purpose**: structural getters (`ADDRESSES_PROVIDER()`,
     `getACLManager()`) crawl deep and confer membership; asset getters (`getReservesList()`)
     mark reserved external assets without recursing into their world.
   - **speculative probing**: struct getters are read even without an ABI (works on
     bytecode-only and exotic chains).
   - **reserve-keyed expansion**: `getReserveData(asset)` over the reserve list surfaces each
     aToken, debt token and rate strategy (generalizes to Compound, Euler, Morpho).
   - **factory & singleton events**: `Create*` logs enumerate instances; hot singletons are
     read with topic-filtered logs.
   - **diamond facets, role hubs, deployer siblings, cross-chain mirrors and LayerZero peers.**
3. **Membership by control**: the project's authorities (admins, role holders, timelocks,
   multisigs) and deployers form a set that closes iteratively, so a member's own authorities
   pull in the next contract. A bare reference (an external oracle a pool reads) stays external.
4. **Reason (optional)**: an LLM sees the graph, proposes reads to run next, and the
   deterministic layer executes them and merges the results, until it converges.

The graph structure is always **deterministic fact**; the LLM only proposes where to look. It
is **model-agnostic**: any OpenAI-compatible key (DeepSeek, OpenAI, OpenRouter, Groq) or an
Anthropic key / Claude subscription plugs in behind the same port.

**The LLM earns its place: measured, not assumed.** An ablation harness (`evals/ablation.py`)
quantifies exactly what the reasoning loop adds over pure determinism. The honest result: on
source-available protocols the deterministic engine already recovers the structure, so the LLM
adds **~0 new nodes** and contributes a semantic layer (protocol summary, role labels); its
structural value is reserved for genuinely opaque contracts (bytecode-only, no ABI). Two safety
properties make it trustworthy. First, the model can only *propose* a read; every result is
re-derived deterministically on-chain, so even a prompt-injected model **cannot inject a fake
node**. Second, untrusted on-chain text (names, state) is sanitized before it reaches the prompt.

## Architecture

Hexagonal (ports & adapters). A pure `domain/` core (graph model, proxy detection, membership,
clone collapsing, token taxonomy) is stdlib-only and unit-tested without a network. Everything
external sits behind `ports/` with swappable `adapters/` (RPC, source resolvers, activity/trace
providers, LLM).

```
src/dandelion/
├── domain/      pure logic: models · proxies · classify · membership · clones · getters · tokens · …
├── ports/       protocols: RpcPort · SourceResolverPort · ActivityPort · LlmPort
├── adapters/    rpc (JSON-RPC) · sources (etherscan/sourcify/blockscout/heimdall) · activity · llm
├── services/    reconstruct (the crawl) · probes · enrich (the reasoning loop)
└── cli.py       dandelion map …
```

## Development

```bash
pytest                       # 124 unit tests, no network required
ruff check .                 # lint
mypy src/dandelion/domain    # types on the pure core
```

The `evals/` harness replays golden fixtures against live RPC and scores proxy resolution,
naming, node recall, **membership precision** (a leak audit that gates external-asset and
operator-key false positives), mirror coverage and clone collapse across a set of real
protocols (Aave, Fluid, Morpho, Velodrome, deBridge, Liquity, GMX, mETH).

### Generalization (held-out set)

Metrics on the tuning set alone would be circular. `evals/run_evals.py --set holdout` scores
protocols the heuristics were **not** built against. On the first run, with no protocol-specific
tuning, the generic engine mapped **3 of 4**: Spark Lend (an Aave fork at entirely different
addresses) to 40 named nodes, Balancer V2's singleton Vault, and Compound V3's Comet, all at
**precision 1.0**. The one gap is honest: Curve's Vyper `coins(i)` token-list idiom without a
verified ABI. The discovery engine is generic; curated lists only add a boost.

## License

[MIT](LICENSE)
