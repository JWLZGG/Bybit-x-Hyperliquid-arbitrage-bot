from __future__ import annotations

from datetime import datetime, timezone

from bot.data_ingestion.funding_models import FundingRateSnapshot


def test_hyperliquid_hourly_to_8h_equivalent() -> None:
    snap = FundingRateSnapshot(
        exchange="hyperliquid",
        symbol="BTCUSDT",
        raw_rate=0.0001,
        interval_hours=1.0,
        rate_8h_equivalent=0.0008,
        observed_at=datetime.now(timezone.utc),
    )

    assert snap.rate_8h_equivalent == 0.0008
    assert snap.effective_rate_8h_equivalent == 0.0008


def test_bybit_8h_equivalent_unchanged() -> None:
    snap = FundingRateSnapshot(
        exchange="bybit",
        symbol="BTCUSDT",
        raw_rate=0.0003,
        interval_hours=8.0,
        rate_8h_equivalent=0.0003,
        observed_at=datetime.now(timezone.utc),
    )

    assert snap.rate_8h_equivalent == snap.raw_rate


def test_predicted_rate_takes_precedence_when_available() -> None:
    snap = FundingRateSnapshot(
        exchange="bybit",
        symbol="BTCUSDT",
        raw_rate=0.0003,
        interval_hours=8.0,
        rate_8h_equivalent=0.0003,
        observed_at=datetime.now(timezone.utc),
        predicted_rate_8h_equivalent=0.0005,
    )

    assert snap.effective_rate_8h_equivalent == 0.0005
