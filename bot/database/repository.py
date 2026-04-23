from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from bot.database.models import DashboardHealthData, SystemEvent
from bot.database.schema import get_connection
from bot.execution.models import ExecutionResult, PositionPair
from bot.signal_generator.models import Opportunity


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_opportunity(database_path: str, opportunity: Opportunity) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO opportunities (
                timestamp,
                symbol,
                strategy_type,
                gross_expected_bp,
                expected_net_bp,
                total_cost_bp,
                decision,
                reject_reason,
                bybit_value,
                hyperliquid_value,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity.timestamp.isoformat(),
                opportunity.symbol,
                opportunity.strategy_type,
                opportunity.gross_expected_bp,
                opportunity.expected_net_bp,
                opportunity.total_cost_bp,
                opportunity.decision,
                opportunity.reject_reason,
                opportunity.bybit_value,
                opportunity.hyperliquid_value,
                json.dumps(opportunity.metadata, sort_keys=True),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def insert_position_pair(database_path: str, position_pair: PositionPair) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO position_pairs (
                symbol,
                strategy_type,
                bybit_side,
                hyperliquid_side,
                notional_usd,
                entry_time,
                status,
                entry_bybit_price,
                entry_hyperliquid_price,
                current_pnl,
                expected_net_bp,
                delta_imbalance_bp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position_pair.symbol,
                position_pair.strategy_type,
                position_pair.bybit_side,
                position_pair.hyperliquid_side,
                position_pair.notional_usd,
                position_pair.entry_time.isoformat(),
                position_pair.status,
                position_pair.entry_bybit_price,
                position_pair.entry_hyperliquid_price,
                position_pair.current_pnl,
                position_pair.expected_net_bp,
                position_pair.delta_imbalance_bp,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def update_position_pair_status(
    database_path: str,
    position_pair_id: int,
    status: str,
    current_pnl: float | None = None,
    delta_imbalance_bp: float | None = None,
) -> None:
    updates = ["status = ?"]
    params: list[Any] = [status]
    if current_pnl is not None:
        updates.append("current_pnl = ?")
        params.append(current_pnl)
    if delta_imbalance_bp is not None:
        updates.append("delta_imbalance_bp = ?")
        params.append(delta_imbalance_bp)
    params.append(position_pair_id)

    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            UPDATE position_pairs
            SET {", ".join(updates)}
            WHERE id = ?
            """,
            tuple(params),
        )
        connection.commit()
    finally:
        connection.close()


def insert_execution_result(database_path: str, result: ExecutionResult) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO execution_results (
                symbol,
                strategy_type,
                status,
                accepted,
                reason,
                bybit_leg_status,
                hyperliquid_leg_status,
                notional_usd,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.symbol,
                result.strategy_type,
                result.status,
                int(result.accepted),
                result.reason,
                result.bybit_leg.status,
                result.hyperliquid_leg.status,
                result.notional_usd,
                json.dumps(result.metadata, sort_keys=True),
                result.created_at.isoformat(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def insert_system_event(database_path: str, event: SystemEvent) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO system_events (
                timestamp,
                level,
                event_type,
                message,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.timestamp.isoformat(),
                event.level,
                event.event_type,
                event.message,
                json.dumps(event.metadata, sort_keys=True),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_recent_opportunities(database_path: str, limit: int = 100) -> list[Opportunity]:
    rows = _fetch_rows(
        database_path,
        """
        SELECT *
        FROM opportunities
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_row_to_opportunity(row) for row in rows]


def get_open_positions(database_path: str) -> list[PositionPair]:
    rows = _fetch_rows(
        database_path,
        """
        SELECT *
        FROM position_pairs
        WHERE status IN ('OPEN', 'DEGRADED')
        ORDER BY id DESC
        """,
        (),
    )
    return [_row_to_position_pair(row) for row in rows]


def get_recent_positions(database_path: str, limit: int = 100) -> list[PositionPair]:
    rows = _fetch_rows(
        database_path,
        """
        SELECT *
        FROM position_pairs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_row_to_position_pair(row) for row in rows]


def get_recent_execution_results(database_path: str, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_rows(
        database_path,
        """
        SELECT *
        FROM execution_results
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def get_daily_rejection_counts(database_path: str) -> dict[str, int]:
    rows = _fetch_rows(
        database_path,
        """
        SELECT decision, COUNT(*) AS count
        FROM opportunities
        WHERE DATE(timestamp) = DATE('now')
        GROUP BY decision
        """,
        (),
    )
    return {row["decision"]: int(row["count"]) for row in rows}


def get_recent_system_events(database_path: str, limit: int = 100) -> list[SystemEvent]:
    rows = _fetch_rows(
        database_path,
        """
        SELECT *
        FROM system_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_row_to_system_event(row) for row in rows]


def get_dashboard_health_data(database_path: str) -> DashboardHealthData:
    latest_heartbeats = _fetch_rows(
        database_path,
        """
        SELECT source, status, created_at
        FROM heartbeat
        ORDER BY id DESC
        LIMIT 10
        """,
        (),
    )
    heartbeat_map: dict[str, dict[str, Any]] = {}
    for row in latest_heartbeats:
        heartbeat_map.setdefault(row["source"], row)

    latest_latency_rows = _fetch_rows(
        database_path,
        """
        SELECT exchange, latency_ms, observed_at
        FROM market_snapshots
        ORDER BY id DESC
        LIMIT 20
        """,
        (),
    )
    latency_map: dict[str, dict[str, Any]] = {}
    for row in latest_latency_rows:
        latency_map.setdefault(row["exchange"], row)

    system_events = get_recent_system_events(database_path, limit=10)
    latest_health_event = next(
        (event for event in system_events if event.event_type == "system_health"),
        None,
    )
    bot_state = latest_health_event.metadata.get("bot_state", "unknown") if latest_health_event else "unknown"
    paused = bot_state == "paused"

    return DashboardHealthData(
        bot_state=bot_state,
        bybit_status=heartbeat_map.get("bybit", {}).get("status", "unknown"),
        hyperliquid_status=heartbeat_map.get("hyperliquid", {}).get("status", "unknown"),
        bybit_latency_ms=latency_map.get("bybit", {}).get("latency_ms"),
        hyperliquid_latency_ms=latency_map.get("hyperliquid", {}).get("latency_ms"),
        paused=paused,
        last_updated=latest_health_event.timestamp.isoformat() if latest_health_event else None,
    )


def insert_heartbeat(database_path: str, source: str, status: str) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO heartbeat (source, status, created_at)
            VALUES (?, ?, ?)
            """,
            (source, status, _utc_now_iso()),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def insert_market_snapshot(
    database_path: str,
    exchange: str,
    symbol: str,
    last_price: float,
    mark_price: float,
    index_price: float | None,
    latency_ms: float | None,
    orderbook_depth_usd: float | None,
    observed_at: str,
) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO market_snapshots (
                exchange,
                symbol,
                last_price,
                mark_price,
                index_price,
                latency_ms,
                orderbook_depth_usd,
                observed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exchange,
                symbol,
                last_price,
                mark_price,
                index_price,
                latency_ms,
                orderbook_depth_usd,
                observed_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def insert_funding_snapshot(
    database_path: str,
    exchange: str,
    symbol: str,
    raw_rate: float,
    interval_hours: float,
    rate_8h_equivalent: float,
    predicted_rate_8h_equivalent: float | None,
    latency_ms: float | None,
    observed_at: str,
) -> int:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO funding_snapshots (
                exchange,
                symbol,
                raw_rate,
                interval_hours,
                rate_8h_equivalent,
                predicted_rate_8h_equivalent,
                latency_ms,
                observed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exchange,
                symbol,
                raw_rate,
                interval_hours,
                rate_8h_equivalent,
                predicted_rate_8h_equivalent,
                latency_ms,
                observed_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def _fetch_rows(
    database_path: str,
    query: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def _row_to_opportunity(row: dict[str, Any]) -> Opportunity:
    metadata = json.loads(row["metadata_json"]) if row.get("metadata_json") else {}
    return Opportunity(
        id=row.get("id"),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        symbol=row["symbol"],
        strategy_type=row["strategy_type"],
        gross_expected_bp=row["gross_expected_bp"],
        expected_net_bp=row["expected_net_bp"],
        total_cost_bp=row["total_cost_bp"],
        decision=row["decision"],
        reject_reason=row["reject_reason"],
        bybit_value=row["bybit_value"],
        hyperliquid_value=row["hyperliquid_value"],
        metadata=metadata,
    )


def _row_to_position_pair(row: dict[str, Any]) -> PositionPair:
    return PositionPair(
        id=row.get("id"),
        symbol=row["symbol"],
        strategy_type=row["strategy_type"],
        bybit_side=row["bybit_side"],
        hyperliquid_side=row["hyperliquid_side"],
        notional_usd=row["notional_usd"],
        entry_time=datetime.fromisoformat(row["entry_time"]),
        status=row["status"],
        entry_bybit_price=row["entry_bybit_price"],
        entry_hyperliquid_price=row["entry_hyperliquid_price"],
        current_pnl=row["current_pnl"],
        expected_net_bp=row["expected_net_bp"],
        delta_imbalance_bp=row.get("delta_imbalance_bp") or 0.0,
    )


def _row_to_system_event(row: dict[str, Any]) -> SystemEvent:
    metadata = json.loads(row["metadata_json"]) if row.get("metadata_json") else {}
    return SystemEvent(
        id=row.get("id"),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        level=row["level"],
        event_type=row["event_type"],
        message=row["message"],
        metadata=metadata,
    )
