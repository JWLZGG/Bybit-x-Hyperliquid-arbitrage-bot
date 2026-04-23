from __future__ import annotations

from datetime import datetime, timezone

from bot.config.config import load_config
from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.signal_generator.funding_strategy import (
    build_funding_snapshot,
    calculate_funding_diff_bp,
    determine_pair_sides,
    maybe_emit_trade_intent,
    normalise_hyperliquid_to_8h,
)


def _load_test_config(monkeypatch):
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")
    return load_config()


def test_hyperliquid_hourly_rate_normalizes_to_eight_hours(monkeypatch) -> None:
    _load_test_config(monkeypatch)
    assert normalise_hyperliquid_to_8h(0.0002) == 0.0016


def test_correct_side_selection_longs_lower_funding_exchange(monkeypatch) -> None:
    _load_test_config(monkeypatch)
    snapshot = build_funding_snapshot(
        FundingRateSnapshot(
            exchange="bybit",
            symbol="BTCUSDT",
            raw_rate=0.0001,
            interval_hours=8.0,
            rate_8h_equivalent=0.0001,
            observed_at=datetime.now(timezone.utc),
        ),
        FundingRateSnapshot(
            exchange="hyperliquid",
            symbol="BTCUSDT",
            raw_rate=0.0004,
            interval_hours=1.0,
            rate_8h_equivalent=0.0032,
            observed_at=datetime.now(timezone.utc),
        ),
    )
    assert determine_pair_sides(snapshot) == ("Buy", "Sell")


def test_threshold_handling_emits_trade_intent_only_when_above_threshold(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    snapshot = build_funding_snapshot(
        FundingRateSnapshot(
            exchange="bybit",
            symbol="BTCUSDT",
            raw_rate=0.0001,
            interval_hours=8.0,
            rate_8h_equivalent=0.0001,
            observed_at=datetime.now(timezone.utc),
        ),
        FundingRateSnapshot(
            exchange="hyperliquid",
            symbol="BTCUSDT",
            raw_rate=0.0004,
            interval_hours=1.0,
            rate_8h_equivalent=0.0032,
            observed_at=datetime.now(timezone.utc),
        ),
    )
    opportunity, trade_intent = maybe_emit_trade_intent(snapshot, config, 2_000.0)
    assert abs(calculate_funding_diff_bp(snapshot)) >= config.funding_diff_threshold_bp
    assert opportunity.decision == "accepted"
    assert trade_intent is not None


def test_reject_path_returns_near_miss_or_net_positive_rejection(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    snapshot = build_funding_snapshot(
        FundingRateSnapshot(
            exchange="bybit",
            symbol="BTCUSDT",
            raw_rate=0.0001,
            interval_hours=8.0,
            rate_8h_equivalent=0.0001,
            observed_at=datetime.now(timezone.utc),
        ),
        FundingRateSnapshot(
            exchange="hyperliquid",
            symbol="BTCUSDT",
            raw_rate=0.0002,
            interval_hours=1.0,
            rate_8h_equivalent=0.0016,
            observed_at=datetime.now(timezone.utc),
        ),
    )
    opportunity, trade_intent = maybe_emit_trade_intent(snapshot, config, 2_000.0)
    assert opportunity.decision in {"near_miss", "rejected_net_positive"}
    assert trade_intent is None
