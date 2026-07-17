"""Unit tests for LLM provider selection and auth modes (no network)."""
import pytest

from dandelion.adapters.llm.anthropic import AnthropicLLM
from dandelion.adapters.llm.factory import build_llm
from dandelion.adapters.llm.openai_compat import OpenAICompatLLM


def test_subscription_oauth_headers():
    llm = AnthropicLLM(model="claude-sonnet-5", oauth_token="tok123")
    assert llm.auth_mode == "oauth"
    h = llm._headers()
    assert h["authorization"] == "Bearer tok123"
    assert h["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-api-key" not in h


def test_api_key_headers(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    llm = AnthropicLLM(model="claude-sonnet-5", api_key="sk-ant")
    assert llm.auth_mode == "api_key"
    h = llm._headers()
    assert h["x-api-key"] == "sk-ant"
    assert "authorization" not in h


def test_anthropic_requires_some_auth(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError):
        AnthropicLLM(model="claude-sonnet-5")


def test_factory_picks_anthropic_subscription():
    llm = build_llm("anthropic:claude-sonnet-5", oauth_token="tok")
    assert isinstance(llm, AnthropicLLM) and llm.auth_mode == "oauth"


def test_factory_picks_anthropic_apikey_via_claude_alias(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    llm = build_llm("claude:claude-opus-4-8", api_key="sk-ant")
    assert isinstance(llm, AnthropicLLM) and llm.auth_mode == "api_key"


def test_factory_picks_openai_compatible():
    llm = build_llm("deepseek:deepseek-chat", api_key="k")
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.provider == "deepseek"
    assert "deepseek.com" in (llm.base_url or "")
