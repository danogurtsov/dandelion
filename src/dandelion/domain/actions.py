"""
Typed LLM actions — pure core (no I/O).

The LLM never writes to the graph. It may only return actions from this closed vocabulary,
each of which maps 1:1 to a deterministic read primitive. The service layer (membrane) executes
and validates them; here we only define the vocabulary and normalize/validate their shape, so a
malformed or injected proposal is dropped before it can do anything.

  read_addr        name()               -> one address       (struct/asset/generic getter)
  read_addr_array  name()               -> address[]         (reserve/token list)
  enumerate_index  name(uint256)        -> address per index  (Vyper coins(i), registry-by-index)
  reserve_keyed    name(address)        -> struct w/ addrs    (Aave getReserveData, Compound markets)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("read_addr", "read_addr_array", "enumerate_index", "reserve_keyed")
PURPOSES = ("struct", "asset", "generic")

# per-kind signature shape (a single clean function signature, no smuggled extras)
_SHAPE = {
    "read_addr": re.compile(r"^([A-Za-z_]\w*)\(\)$"),
    "read_addr_array": re.compile(r"^([A-Za-z_]\w*)\(\)$"),
    "enumerate_index": re.compile(r"^([A-Za-z_]\w*)\((?:uint256|uint)\)$"),
    "reserve_keyed": re.compile(r"^([A-Za-z_]\w*)\(address\)$"),
}


@dataclass(frozen=True)
class Action:
    key: str          # node key '<chain>:<addr>' the action targets
    kind: str         # one of KINDS
    sig: str          # normalized signature
    purpose: str = "generic"   # struct | asset | generic (feeds purpose-aware membership)
    cap: int = 40     # for enumerate_index / list caps

    @property
    def name(self) -> str:
        return self.sig.split("(", 1)[0]


def _clean_sig(kind: str, raw: str | None) -> str | None:
    """
    Normalize to exactly one well-formed signature for `kind`, else None. Strips whitespace and
    requires the WHOLE string to match the kind's shape — trailing prose / smuggled extra calls
    are rejected, not silently accepted.
    """
    if not raw:
        return None
    cand = re.sub(r"\s+", "", str(raw))
    shape = _SHAPE.get(kind)
    return cand if (shape and shape.fullmatch(cand)) else None


def parse_actions(items: list[dict] | None) -> list[Action]:
    """Validate LLM-returned action dicts into typed Actions, dropping anything malformed."""
    out: list[Action] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind", "")).strip()
        key = str(it.get("key", "")).strip()
        if kind not in KINDS or not key:
            continue
        sig = _clean_sig(kind, it.get("sig") or it.get("read"))
        if not sig:
            continue
        purpose = str(it.get("purpose", "generic")).strip()
        if purpose not in PURPOSES:
            purpose = "generic"
        try:
            cap = int(it.get("cap", 40))
        except (TypeError, ValueError):
            cap = 40
        out.append(Action(key=key, kind=kind, sig=sig, purpose=purpose, cap=max(1, min(cap, 60))))
    return out
