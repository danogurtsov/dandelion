"""
OpenChain selector directory (keyless) — resolve 4-byte selectors to function signatures.

Turns an opaque contract's raw selectors into readable signatures for the LLM prompt. Keyless,
cached in-process, graceful (any failure yields no name — never raises). Only the first candidate
signature per selector is used; ambiguity is acceptable here (the LLM's proposals are validated
deterministically by the membrane anyway).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

_LOOKUP = "https://api.openchain.xyz/signature-database/v1/lookup"


def parse_lookup(body: dict) -> dict[str, str]:
    """OpenChain lookup response -> {selector: first-signature}."""
    out: dict[str, str] = {}
    fns = ((body.get("result") or {}).get("function")) or {}
    for sel, cands in fns.items():
        if isinstance(cands, list) and cands:
            name = cands[0].get("name")
            if name:
                out[sel.lower()] = name
    return out


@dataclass
class OpenChainSelectors:
    timeout: float = 15.0
    _cache: dict[str, str] = field(default_factory=dict, init=False)

    async def resolve(self, selectors: list[str], *, cap: int = 24) -> dict[str, str]:
        """Resolve selectors to signatures ({sel: sig}); cached, graceful, best-effort."""
        want = [s.lower() for s in selectors[:cap] if s.lower() not in self._cache]
        if want:
            params = [("function", s) for s in want] + [("filter", "true")]
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.get(_LOOKUP, params=params, headers={"User-Agent": "dandelion"})
                r.raise_for_status()
                self._cache.update(parse_lookup(r.json()))
            except Exception:  # noqa: BLE001
                pass
        return {s.lower(): self._cache[s.lower()] for s in selectors if s.lower() in self._cache}
