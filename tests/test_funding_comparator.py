from __future__ import annotations

from datetime import datetime, timezone

from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.signal_generator.funding_comparator import compare_funding_opportunity


def test_compare_funding_opportunity_bybit_long_hyperliquid_short() -> None:
    bybit = FundingRateSnapshot(
        exchange="bybit",
        symbol="BTCUSDT",
        raw_rate=0.0001,
        interval_hours=8.0,
        rate_8h_equivalent=0.0001,
        observed_at=datetime.now(timezone.utc),
    )
    hyperliquid = FundingRateSnapshot(
        exchange="hyperliquid",
        symbol="BTCUSDT",
        raw_rate=0.0008,
        interval_hours=1.0,
        rate_8h_equivalent=0.0064,
        observed_at=datetime.now(timezone.utc),
    )

    opp = compare_funding_opportunity(bybit, hyperliquid, entry_threshold_bp=5.0)

    assert opp.long_exchange == "bybit"
    assert opp.short_exchange == "hyperliquid"
    assert opp.meets_entry_threshold is True
    assert opp.gross_expected_bp == abs(opp.normalized_diff_bp)


def test_compare_funding_opportunity_hyperliquid_long_bybit_short() -> None:
    bybit = FundingRateSnapshot(
        exchange="bybit",
        symbol="SOLUSDT",
        raw_rate=0.0040,
        interval_hours=8.0,
        rate_8h_equivalent=0.0040,
        observed_at=datetime.now(timezone.utc),
    )
    hyperliquid = FundingRateSnapshot(
        exchange="hyperliquid",
        symbol="SOLUSDT",
        raw_rate=0.0001,
        interval_hours=1.0,
        rate_8h_equivalent=0.0008,
        observed_at=datetime.now(timezone.utc),
    )

    opp = compare_funding_opportunity(bybit, hyperliquid, entry_threshold_bp=5.0)

    assert opp.long_exchange == "hyperliquid"
    assert opp.short_exchange == "bybit"
    assert opp.meets_entry_threshold is True
    assert opp.gross_expected_bp == abs(opp.normalized_diff_bp)
