from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from bot.database.models import SystemEvent
from bot.database.repository import (
    get_dashboard_health_data,
    get_daily_rejection_counts,
    get_open_positions,
    get_recent_execution_results,
    get_recent_positions,
    get_recent_system_events,
    insert_execution_result as repository_insert_execution_result,
    insert_funding_snapshot,
    insert_heartbeat,
    insert_market_snapshot,
    insert_position_pair as repository_insert_position_pair,
    insert_system_event,
)
from bot.database.schema import get_connection, initialize_database
from bot.execution.models import ExecutionResult, LegExecutionResult, PositionPair


def insert_funding_opportunity(
    database_path: str,
    symbol: str,
    bybit_rate_8h: float,
    hyperliquid_rate_8h: float,
    normalized_diff_bp: float,
    gross_expected_bp: float,
    expected_net_bp: float,
    long_exchange: str,
    short_exchange: str,
    meets_entry_threshold: bool,
    will_trade: bool,
    decision_reason: str,
    observed_at: str,
) -> None:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO funding_opportunities (
                symbol,
                bybit_rate_8h,
                hyperliquid_rate_8h,
                normalized_diff_bp,
                gross_expected_bp,
                expected_net_bp,
                long_exchange,
                short_exchange,
                meets_entry_threshold,
                will_trade,
                decision_reason,
                observed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                bybit_rate_8h,
                hyperliquid_rate_8h,
                normalized_diff_bp,
                gross_expected_bp,
                expected_net_bp,
                long_exchange,
                short_exchange,
                int(meets_entry_threshold),
                int(will_trade),
                decision_reason,
                observed_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def insert_scanner_event(
    database_path: str,
    strategy_type: str,
    symbol: str,
    event_type: str,
    decision_state: str,
    long_exchange: str,
    short_exchange: str,
    gross_expected_bp: float,
    expected_net_bp: float,
    threshold_bp: float,
    reference_value_bp: float,
    total_cost_bp: float,
    will_trade: bool,
    decision_reason: str,
    observed_at: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO scanner_events (
                strategy_type,
                symbol,
                event_type,
                decision_state,
                long_exchange,
                short_exchange,
                gross_expected_bp,
                expected_net_bp,
                threshold_bp,
                reference_value_bp,
                total_cost_bp,
                will_trade,
                decision_reason,
                metadata_json,
                observed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_type,
                symbol,
                event_type,
                decision_state,
                long_exchange,
                short_exchange,
                gross_expected_bp,
                expected_net_bp,
                threshold_bp,
                reference_value_bp,
                total_cost_bp,
                int(will_trade),
                decision_reason,
                json.dumps(metadata or {}, sort_keys=True),
                observed_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def insert_execution_result(
    database_path: str,
    symbol: str,
    accepted: bool,
    long_exchange: str,
    short_exchange: str,
    notional_usd: float,
    strategy: str,
    status: str,
    reason: str,
    created_at: str,
) -> None:
    long_side = "Buy" if long_exchange == "bybit" else "Sell"
    short_side = "Sell" if long_exchange == "bybit" else "Buy"
    result = ExecutionResult(
        symbol=symbol,
        strategy_type=strategy,
        status=status,
        accepted=accepted,
        reason=reason,
        bybit_leg=LegExecutionResult(
            exchange="bybit",
            side=long_side if long_exchange == "bybit" else short_side,
            order_id="legacy-bybit",
            requested_notional_usd=notional_usd,
            filled_notional_usd=notional_usd if accepted else 0.0,
            average_fill_price=0.0,
            status=status,
        ),
        hyperliquid_leg=LegExecutionResult(
            exchange="hyperliquid",
            side=long_side if long_exchange == "hyperliquid" else short_side,
            order_id="legacy-hyperliquid",
            requested_notional_usd=notional_usd,
            filled_notional_usd=notional_usd if accepted else 0.0,
            average_fill_price=0.0,
            status=status,
        ),
        created_at=datetime.fromisoformat(created_at),
        metadata={"legacy_long_exchange": long_exchange, "legacy_short_exchange": short_exchange},
    )
    repository_insert_execution_result(database_path, result)


def insert_position_pair(
    database_path: str,
    symbol: str,
    bybit_side: str,
    hyperliquid_side: str,
    notional_usd: float,
    entry_time: str,
    current_pnl: float,
    strategy: str,
    status: str,
) -> None:
    repository_insert_position_pair(
        database_path,
        PositionPair(
            symbol=symbol,
            strategy_type=strategy,
            bybit_side=bybit_side,
            hyperliquid_side=hyperliquid_side,
            notional_usd=notional_usd,
            entry_time=datetime.fromisoformat(entry_time),
            status=status,
            entry_bybit_price=0.0,
            entry_hyperliquid_price=0.0,
            current_pnl=current_pnl,
            expected_net_bp=0.0,
        ),
    )


def fetch_dashboard_summary(database_path: str) -> dict[str, Any]:
    health = get_dashboard_health_data(database_path)
    rejection_counts = get_daily_rejection_counts(database_path)
    return {
        "bot_state": health.bot_state,
        "opportunities_today": sum(rejection_counts.values()),
        "near_misses_today": rejection_counts.get("near_miss", 0),
        "trade_candidates_today": rejection_counts.get("accepted", 0) + rejection_counts.get("executed", 0),
        "rejected_opportunities_today": rejection_counts.get("rejected_net_positive", 0) + rejection_counts.get("rejected_risk", 0),
        "open_positions": len(get_open_positions(database_path)),
        "accepted_executions": len([row for row in get_recent_execution_results(database_path, 100) if row["accepted"]]),
    }


def fetch_recent_scanner_events(database_path: str, limit: int = 25) -> list[dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM scanner_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def fetch_recent_execution_results(database_path: str, limit: int = 25) -> list[dict[str, Any]]:
    return get_recent_execution_results(database_path, limit)


def fetch_recent_position_pairs(database_path: str, limit: int = 25) -> list[dict[str, Any]]:
    return [position.__dict__ for position in get_recent_positions(database_path, limit)]


def fetch_latest_heartbeats(database_path: str) -> list[dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT source, status, created_at
            FROM heartbeat
            ORDER BY id DESC
            LIMIT 10
            """
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()
