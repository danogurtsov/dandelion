"""
LLM factory — build an LlmPort from a `provider:model` string.

One call for every variant:
  • Claude subscription   — spec="anthropic:claude-sonnet-5" + CLAUDE_CODE_OAUTH_TOKEN
  • Anthropic API key      — spec="anthropic:claude-sonnet-5" + ANTHROPIC_API_KEY
  • any OpenAI-compatible  — spec="deepseek:deepseek-chat" (+ DEEPSEEK_API_KEY), etc.
To the caller the result is the same — an LlmPort.
"""
from __future__ import annotations

from ...ports import LlmPort
from .anthropic import AnthropicLLM
from .openai_compat import OpenAICompatLLM

_ANTHROPIC = {"anthropic", "claude"}


def build_llm(
    spec: str,
    *,
    api_key: str | None = None,
    oauth_token: str | None = None,
    base_url: str | None = None,
) -> LlmPort:
    """spec = 'provider:model'. Auth is taken from the arguments or from env by the adapter."""
    provider, _, model = spec.partition(":")
    provider = provider.lower().strip()
    model = model.strip()

    if provider in _ANTHROPIC:
        return AnthropicLLM(
            model=model or "claude-sonnet-5",
            api_key=api_key,
            oauth_token=oauth_token,
            base_url=base_url or "https://api.anthropic.com/v1",
        )
    # everything else — the OpenAI-compatible path (deepseek/openai/openrouter/groq/local/…)
    return OpenAICompatLLM(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
    )
