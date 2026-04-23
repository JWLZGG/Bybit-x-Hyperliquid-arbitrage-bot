from __future__ import annotations

from dataclasses import dataclass

from bot.data_ingestion.funding_models import FundingRateSnapshot


@dataclass(frozen=True)
class FundingOpportunity:
    symbol: str
    bybit_rate_8h: float
    hyperliquid_rate_8h: float
    normalized_diff_bp: float
    gross_expected_bp: float
    long_exchange: str
    short_exchange: str
    meets_entry_threshold: bool


def compare_funding_opportunity(
    bybit_snapshot: FundingRateSnapshot,
    hyperliquid_snapshot: FundingRateSnapshot,
    entry_threshold_bp: float,
) -> FundingOpportunity:
    if bybit_snapshot.symbol != hyperliquid_snapshot.symbol:
        raise ValueError("Funding snapshots must refer to the same symbol")

    bybit_rate = bybit_snapshot.effective_rate_8h_equivalent
    hyperliquid_rate = hyperliquid_snapshot.effective_rate_8h_equivalent
    diff_bp = (hyperliquid_rate - bybit_rate) * 10_000

    # Lower funding side should be long, higher funding side should be short
    if bybit_rate <= hyperliquid_rate:
        long_exchange = "bybit"
        short_exchange = "hyperliquid"
    else:
        long_exchange = "hyperliquid"
        short_exchange = "bybit"

    return FundingOpportunity(
        symbol=bybit_snapshot.symbol,
        bybit_rate_8h=bybit_rate,
        hyperliquid_rate_8h=hyperliquid_rate,
        normalized_diff_bp=diff_bp,
        gross_expected_bp=abs(diff_bp),
        long_exchange=long_exchange,
        short_exchange=short_exchange,
        meets_entry_threshold=abs(diff_bp) >= entry_threshold_bp,
    )
