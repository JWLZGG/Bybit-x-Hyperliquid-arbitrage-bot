from datetime import datetime, timedelta, timezone

from bot.risk_engine.market_state import MarketStateTracker


def test_market_state_tracker_records_price_and_depth_history() -> None:
    tracker = MarketStateTracker(history_window_seconds=60)
    now = datetime.now(timezone.utc)

    tracker.record_price("bybit", "BTCUSDT", 100.0, now - timedelta(seconds=30))
    tracker.record_price("bybit", "BTCUSDT", 102.0, now)
    tracker.record_depth("bybit", "BTCUSDT", 100_000.0, now - timedelta(seconds=30))
    tracker.record_depth("bybit", "BTCUSDT", 200_000.0, now)

    assert tracker.one_minute_move_pct("bybit", "BTCUSDT") == 2.0
    assert tracker.average_depth_usd("bybit", "BTCUSDT") == 150_000.0
