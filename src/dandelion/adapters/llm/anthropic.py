"""
Anthropic LLM adapter — two auth modes, one interface.

1) Claude subscription: CLAUDE_CODE_OAUTH_TOKEN → Authorization: Bearer + anthropic-beta
   (as in Claude Code / the monorepo's KB service). We do NOT send x-api-key.
2) API key: ANTHROPIC_API_KEY → x-api-key.

The choice follows whatever is set (oauth takes priority). To the LlmPort caller
it behaves identically in both cases.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from ...ports import LlmMessage

# in oauth mode Anthropic requires the Claude Code system prompt as the first block
_CLAUDE_CODE_SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."


@dataclass
class AnthropicLLM:
    model: str
    api_key: str | None = None
    oauth_token: str | None = None
    base_url: str = "https://api.anthropic.com/v1"
    version: str = "2023-06-01"
    timeout: float = 120.0

    def __post_init__(self) -> None:
        self.oauth_token = self.oauth_token or os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
        self.api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not (self.oauth_token or self.api_key):
            raise ValueError("anthropic: set CLAUDE_CODE_OAUTH_TOKEN (subscription) or ANTHROPIC_API_KEY")

    @property
    def auth_mode(self) -> str:
        return "oauth" if self.oauth_token else "api_key"

    def _headers(self) -> dict[str, str]:
        h = {"anthropic-version": self.version, "content-type": "application/json"}
        if self.oauth_token:
            h["authorization"] = f"Bearer {self.oauth_token}"
            h["anthropic-beta"] = "oauth-2025-04-20"
        else:
            h["x-api-key"] = self.api_key or ""
        return h

    async def complete(self, messages: list[LlmMessage], **kw) -> str:
        systems = [m.content for m in messages if m.role == "system"]
        if self.auth_mode == "oauth":
            systems = [_CLAUDE_CODE_SYSTEM, *systems]  # required first block
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages if m.role in ("user", "assistant")
        ]
        payload: dict = {
            "model": self.model,
            "max_tokens": kw.get("max_tokens", 4096),
            "messages": turns,
        }
        if systems:
            payload["system"] = "\n\n".join(systems)
        if "temperature" in kw:
            payload["temperature"] = kw["temperature"]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/messages", json=payload, headers=self._headers())
            r.raise_for_status()
            body = r.json()
        blocks = body.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
