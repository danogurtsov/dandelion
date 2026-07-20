"""
Diagnostics — pure core (no I/O).

The crawl is graceful: a failed read degrades to "no data" rather than crashing. That is
correct, but silent — you cannot tell "the contract has no such getter" from "the RPC errored".
Diagnostics makes gracefulness observable: every swallowed failure is counted and a capped
sample is kept, so an incomplete graph declares itself instead of looking complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# recognized failure kinds (counters)
_KINDS = ("rpc_errors", "source_misses", "getter_reverts", "log_errors", "decode_failures",
          "llm_rejected")


@dataclass
class Diagnostics:
    rpc_errors: int = 0
    source_misses: int = 0
    getter_reverts: int = 0
    log_errors: int = 0
    decode_failures: int = 0
    llm_rejected: int = 0        # AI-proposed actions rejected by the validation membrane
    samples: list[str] = field(default_factory=list)

    def note(self, kind: str, where: str = "", err: object = "") -> None:
        if kind in _KINDS:
            setattr(self, kind, getattr(self, kind) + 1)
        if len(self.samples) < 25:
            self.samples.append(f"{kind} {where}: {str(err)[:80]}".strip())

    def total(self) -> int:
        return sum(getattr(self, k) for k in _KINDS)

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in _KINDS if getattr(self, k)}
        if self.samples:
            d["samples"] = self.samples
        return d

    def summary_line(self) -> str:
        parts = [f"{k}={getattr(self, k)}" for k in _KINDS if getattr(self, k)]
        return "diagnostics: " + ", ".join(parts) if parts else ""
