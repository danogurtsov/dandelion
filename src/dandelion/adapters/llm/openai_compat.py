"""
OpenAI-compatible LLM adapter — "any model key" in a single line.

Covers DeepSeek, OpenAI, OpenRouter, Groq, Together, xAI, Moonshot and any
local OpenAI-compatible endpoint: the only difference is base_url + api_key + model.
Anthropic has its own adapter (a different protocol).

Adding a provider = adding an entry to KNOWN_BASES (or setting base_url in the config).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from ...ports import LlmMessage

# provider name -> (base_url, key env variable)
KNOWN_BASES: dict[str, tuple[str, str]] = {
    "openai":     ("https://api.openai.com/v1",        "OPENAI_API_KEY"),
    "deepseek":   ("https://api.deepseek.com/v1",      "DEEPSEEK_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",     "OPENROUTER_API_KEY"),
    "groq":       ("https://api.groq.com/openai/v1",   "GROQ_API_KEY"),
    "together":   ("https://api.together.xyz/v1",      "TOGETHER_API_KEY"),
    "xai":        ("https://api.x.ai/v1",              "XAI_API_KEY"),
    "moonshot":   ("https://api.moonshot.ai/v1",       "MOONSHOT_API_KEY"),
    "local":      ("http://localhost:11434/v1",        "LOCAL_API_KEY"),  # ollama, etc.
}


@dataclass
class OpenAICompatLLM:
    """
    provider — a key from KNOWN_BASES (e.g. "deepseek") OR arbitrary, if base_url is set.
    """
    model: str
    provider: str = "openai"
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 120.0

    def __post_init__(self) -> None:
        base, env = KNOWN_BASES.get(self.provider, (self.base_url, ""))
        self.base_url = (self.base_url or base or "").rstrip("/")
        self.api_key = self.api_key or (os.getenv(env) if env else None)
        if not self.base_url:
            raise ValueError(f"unknown provider '{self.provider}' and no base_url given")

    async def complete(self, messages: list[LlmMessage], **kw) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kw.get("temperature", 0.0),
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/chat/completions",
                                  json=payload, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
