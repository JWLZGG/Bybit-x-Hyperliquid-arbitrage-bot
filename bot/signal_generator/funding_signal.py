from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FundingSignal:
    symbol: str
    bybit_rate_8h: float
    hyperliquid_rate_8h: float
    normalized_diff_bp: float
    gross_expected_bp: float
    long_exchange: str
    short_exchange: str
    meets_entry_threshold: bool
    reason: str
