"""
Config — pydantic-settings, layered (env / .env). Providers and budgets live here
so behavior can change without touching code.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Budgets(BaseSettings):
    """Caps against combinatorial explosion and cost."""
    max_nodes: int = 400
    crawl_depth: int = 3
    clone_cap: int = 50
    clone_min_group: int = 4
    max_logs: int = 50_000
    max_recent_txs: int = 25


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DANDELION_", env_file=".env", extra="ignore"
    )

    # --- providers (adapter selection) --- #
    rpc_provider: str = "drpc"                 # drpc | alchemy | custom
    source_provider: str = "etherscan_v2"      # etherscan_v2 | sourcify | blockscout
    activity_provider: str = "hypersync"       # hypersync | etherscan | trace_rpc
    cache_backend: str = "disk"                # disk | redis | none

    # --- LLM (optional): "provider:model", key from the matching env var --- #
    llm: str = "deepseek:deepseek-chat"        # e.g. openai:gpt-5, anthropic:claude-sonnet-5
    llm_base_url: str | None = None            # override the endpoint manually

    # --- secrets are read from env by provider name (see adapters) --- #
    default_chain: int = 1
    rpc_urls: dict[int, str] = Field(default_factory=dict)   # chain -> url (or pool)

    budgets: Budgets = Field(default_factory=Budgets)


def load_settings() -> Settings:
    return Settings()
