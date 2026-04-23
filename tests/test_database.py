from pathlib import Path
from uuid import uuid4

from bot.database.db import (
    fetch_dashboard_summary,
    fetch_recent_scanner_events,
    initialize_database,
    insert_scanner_event,
)


def test_scanner_event_round_trip() -> None:
    db_path = Path.cwd() / f"test-events-{uuid4().hex}.db"
    initialize_database(str(db_path))

    try:
        insert_scanner_event(
            str(db_path),
            strategy_type="funding_arbitrage",
            symbol="BTCUSDT",
            event_type="opportunity",
            decision_state="trade_candidate",
            long_exchange="bybit",
            short_exchange="hyperliquid",
            gross_expected_bp=22.0,
            expected_net_bp=2.0,
            threshold_bp=16.0,
            reference_value_bp=22.0,
            total_cost_bp=20.0,
            will_trade=True,
            decision_reason="Scanner found a tradable opportunity",
            observed_at="2026-04-16T00:00:00+00:00",
            metadata={"source": "test"},
        )

        events = fetch_recent_scanner_events(str(db_path), limit=5)
        summary = fetch_dashboard_summary(str(db_path))

        assert len(events) == 1
        assert events[0]["strategy_type"] == "funding_arbitrage"
        assert summary["trade_candidates_today"] in {0, 1}
    finally:
        if db_path.exists():
            db_path.unlink()
