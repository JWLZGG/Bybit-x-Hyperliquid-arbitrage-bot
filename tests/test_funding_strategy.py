from datetime import datetime, timezone

from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.signal_generator.funding_strategy import build_funding_signal


def test_build_funding_signal_longs_lower_funding_side() -> None:
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

    signal = build_funding_signal(bybit, hyperliquid, entry_threshold_bp=5.0)

    assert signal.long_exchange == "bybit"
    assert signal.short_exchange == "hyperliquid"
    assert signal.meets_entry_threshold is True
    assert signal.gross_expected_bp == abs(signal.normalized_diff_bp)
