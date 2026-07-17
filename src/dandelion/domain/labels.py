"""
Known shared infrastructure — pure core.

Contracts that many projects USE but none owns: base tokens, Permit2,
Multicall, Safe singletons. We mark these EXTERNAL regardless of
references/co-occurrence (a project merely consumes them).
"""
from __future__ import annotations

from .models import norm_addr

# lowercase addresses of shared infra (mostly mainnet + deterministic across all chains)
KNOWN_EXTERNAL: set[str] = {
    # base tokens
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "0x853d955acef822db058eb8505911ed77f175b99e",  # FRAX
    "0x83f20f44975d03b1b09e64809b757c47f942beea",  # sDAI
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",  # wstETH
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH
    # shared infra (deterministic addresses — identical across many chains)
    "0x000000000022d473030f116ddee9f6b43ac78ba3",  # Permit2
    "0xca11bde05977b3631167028862be2a173976ca11",  # Multicall3
    "0x1f98431c8ad98523631ae4a59f267346ea31f984",  # UniswapV3 Factory
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # UniswapV2 Router02
    # Safe singletons (multisig logic, not a project)
    "0xd9db270c1b5e3bd161e8c8503c55ceabee709552",  # GnosisSafe 1.3.0
    "0x41675c099f32341bf84bfc5382af534df5c7461a",  # Safe 1.4.1
    "0x3e5c63644e683549055b9be8653de26e0b4cd36e",  # GnosisSafeL2 1.3.0
}


def is_known_external(addr: str | None) -> bool:
    a = norm_addr(addr)
    return a in KNOWN_EXTERNAL if a else False
