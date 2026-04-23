from __future__ import annotations

import asyncio
from statistics import mean
from time import perf_counter

import aiohttp


BYBIT_URL = "https://api-testnet.bybit.com/v5/market/tickers"
BYBIT_PARAMS = {"category": "linear", "symbol": "BTCUSDT"}
HYPERLIQUID_URL = "https://api.hyperliquid-testnet.xyz/info"
HYPERLIQUID_PAYLOAD = {"type": "allMids"}


async def _measure_get(session: aiohttp.ClientSession, url: str, params: dict[str, str]) -> float:
    started_at = perf_counter()
    async with session.get(url, params=params, timeout=10) as response:
        response.raise_for_status()
        await response.read()
    return (perf_counter() - started_at) * 1000


async def _measure_post(session: aiohttp.ClientSession, url: str, payload: dict[str, str]) -> float:
    started_at = perf_counter()
    async with session.post(url, json=payload, timeout=10) as response:
        response.raise_for_status()
        await response.read()
    return (perf_counter() - started_at) * 1000


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        bybit_samples = [await _measure_get(session, BYBIT_URL, BYBIT_PARAMS) for _ in range(5)]
        hyperliquid_samples = [
            await _measure_post(session, HYPERLIQUID_URL, HYPERLIQUID_PAYLOAD)
            for _ in range(5)
        ]

    print("Latency Check Results")
    print(f"Bybit avg: {mean(bybit_samples):.2f} ms | samples={bybit_samples}")
    print(
        "Hyperliquid avg: "
        f"{mean(hyperliquid_samples):.2f} ms | samples={hyperliquid_samples}"
    )


if __name__ == "__main__":
    asyncio.run(main())
