from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDataSanityResult:
    sane: bool
    relative_diff: float
    reason: str


def check_cross_exchange_price_sanity(
    bybit_reference_price: float,
    hyperliquid_reference_price: float,
    max_relative_diff: float = 0.15,
) -> MarketDataSanityResult:
    if bybit_reference_price <= 0 or hyperliquid_reference_price <= 0:
        return MarketDataSanityResult(
            sane=False,
            relative_diff=0.0,
            reason="Non-positive price detected",
        )

    relative_diff = abs(bybit_reference_price - hyperliquid_reference_price) / hyperliquid_reference_price

    if relative_diff > max_relative_diff:
        return MarketDataSanityResult(
            sane=False,
            relative_diff=relative_diff,
            reason=f"Relative price difference too large: {relative_diff:.2%}",
        )

    return MarketDataSanityResult(
        sane=True,
        relative_diff=relative_diff,
        reason="Cross-exchange price sanity check passed",
    )