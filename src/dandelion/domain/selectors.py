"""
Function-selector extraction from bytecode — pure core (no I/O).

For an opaque contract (no verified source / no ABI) the LLM has almost nothing to reason with.
The dispatcher, though, lists the contract's 4-byte function selectors as PUSH4 immediates. We
scan them out; a selector directory (adapter) can then turn `0x0dfe1681` into `token0()`, giving
the LLM real signatures to propose actions against — the context it was missing.
"""
from __future__ import annotations

# push opcodes we skip over so their immediates are not misread as selectors
_PUSH1, _PUSH32, _PUSH4 = 0x60, 0x7F, 0x63


def extract_selectors(bytecode: str | None, *, cap: int = 40) -> list[str]:
    """
    Scan EVM bytecode for PUSH4 immediates that look like function selectors (the Solidity/Vyper
    dispatcher pushes each 4-byte selector before comparing). Deduplicated, order preserved.
    Skips other PUSHN immediates so their bytes are not misread. Best-effort, no disassembler.
    """
    if not bytecode:
        return []
    b = bytecode[2:] if bytecode.startswith("0x") else bytecode
    try:
        code = bytes.fromhex(b)
    except ValueError:
        return []
    out: list[str] = []
    seen: set[str] = set()
    i, n = 0, len(code)
    while i < n:
        op = code[i]
        if op == _PUSH4:
            imm = code[i + 1:i + 5]
            if len(imm) == 4:
                sel = "0x" + imm.hex()
                if sel not in seen and sel != "0x00000000" and sel != "0xffffffff":
                    seen.add(sel)
                    out.append(sel)
                    if len(out) >= cap:
                        break
            i += 5
        elif _PUSH1 <= op <= _PUSH32:
            i += 1 + (op - _PUSH1 + 1)     # skip this push's immediate
        else:
            i += 1
    return out
