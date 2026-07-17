"""
Decompile fallback — worst-case rung of the source ladder (heimdall-rs).

When a contract is verified nowhere: eth_getCode → heimdall decompile → pseudo-Solidity.
Requires `heimdall` installed on PATH; if it's missing — gracefully None (degradation).
Mirrors the predetection chain (fetch source OR decompile).
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ...ports import SourceInfo


@dataclass
class HeimdallDecompiler:
    timeout: float = 120.0

    async def resolve(self, chain: int, addr: str, code: str | None = None) -> SourceInfo | None:
        if not code or code == "0x" or not shutil.which("heimdall"):
            return None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bc = Path(tmp) / "bytecode.txt"
                bc.write_text(code)
                proc = await asyncio.create_subprocess_exec(
                    "heimdall", "decompile", str(bc), "--output", tmp,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
                out = Path(tmp) / "decompiled.sol"
                source = out.read_text() if out.exists() else None
                if not source:
                    return None
                return SourceInfo(tier="decompiled", name=None, source=source)
        except Exception:  # noqa: BLE001
            return None
