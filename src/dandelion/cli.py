"""CLI (Typer). `dandelion map <addr> --chain 1 --rpc <url>` — graph reconstruction."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from . import __version__

app = typer.Typer(add_completion=False, help="Reconstruct a protocol's on-chain architecture from addresses.")


@app.command()
def version() -> None:
    """Print version."""
    typer.echo(f"dandelion {__version__}")


@app.command()
def map(  # noqa: A001 - CLI command name
    addresses: list[str] = typer.Argument(..., help="Contract addresses (seed set)."),
    chain: int = typer.Option(1, help="Chain id of the seeds."),
    rpc: str | None = typer.Option(None, envvar="ETH_RPC_URL", help="JSON-RPC URL for the seed chain."),
    out: str = typer.Option("out.graph.json", help="Output path for the ArchitectureGraph JSON."),
    max_nodes: int | None = typer.Option(
        None, help="Optional safety cap on nodes (default: unbounded — crawl everything "
                   "suspected to be part of the project; explosion bounded by clone-collapse)."),
    etherscan: bool | None = typer.Option(
        None, "--etherscan/--no-etherscan",
        help="Force Etherscan source step on/off (default: auto — on if ETHERSCAN_API_KEY set)."),
    activity: bool = typer.Option(
        True, "--activity/--no-activity",
        help="Use Blockscout activity (deployer/top-callers/co-occurrence) for discovery."),
    audit: bool = typer.Option(False, help="Print the membership precision audit (leaked-member list)."),
    enrich: bool = typer.Option(False, help="Run the LLM reasoning loop (semantic labels + probes + expansion)."),
    rounds: int = typer.Option(2, help="Reasoning rounds for --enrich (determinism<->LLM)."),
    llm: str = typer.Option(
        "anthropic:claude-sonnet-5",
        help="LLM spec provider:model for --enrich (e.g. anthropic:claude-opus-4-8 for hardest reasoning).",
    ),
) -> None:
    """Reconstruct the on-chain architecture graph for the given addresses."""
    if not rpc:
        typer.echo("error: provide --rpc <url> or set ETH_RPC_URL")
        raise typer.Exit(code=2)

    import os as _os

    from .adapters.activity.blockscout import BlockscoutActivity
    from .adapters.activity.composite import CompositeActivity
    from .adapters.activity.etherscan import EtherscanActivity
    from .adapters.rpc.jsonrpc import JsonRpcClient
    from .adapters.sources.ladder import default_ladder
    from .services.reconstruct import reconstruct

    client = JsonRpcClient(rpc_urls={chain: rpc})
    seeds = [(chain, a) for a in addresses]
    ladder = default_ladder(use_etherscan=etherscan)
    # activity: Blockscout keyless + Etherscan deployer (if Etherscan isn't disabled and a key is set)
    act = None
    if activity:
        providers: list = [BlockscoutActivity()]
        if etherscan is not False and _os.getenv("ETHERSCAN_API_KEY"):
            providers.append(EtherscanActivity())
        act = CompositeActivity(providers=providers) if len(providers) > 1 else providers[0]

    async def _run():
        graph = await reconstruct(
            seeds, client, max_nodes=max_nodes, probe_chains=[chain],
            source=ladder, activity=act,
        )
        if enrich:
            from .adapters.llm.factory import build_llm
            from .services.enrich import reason_loop
            await reason_loop(graph, client, build_llm(llm),
                              source=ladder, rounds=rounds)
        return graph

    graph = asyncio.run(_run())
    Path(out).write_text(graph.to_json())
    typer.echo(graph.summary())
    if graph.meta.get("protocol"):
        typer.echo("protocol: " + graph.meta["protocol"])
    if audit:
        from .domain.audit import membership_audit
        au = membership_audit(graph)
        typer.echo(f"\nprecision audit: {au.precision_proxy}  "
                   f"leaked {au.leaked_members}/{au.total_members} members")
        for key, name, reason in au.leaks:
            typer.echo(f"  leak {key} ({name}): {reason}")
    typer.echo(f"-> {out}")


if __name__ == "__main__":
    app()
