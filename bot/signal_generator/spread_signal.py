from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpreadSignal:
    symbol: str
    bybit_price: float
    hyperliquid_price: float
    spread_bp: float
    gross_expected_bp: float
    long_exchange: str
    short_exchange: str
    meets_entry_threshold: bool
    reason: str
