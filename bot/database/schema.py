from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def initialize_schema(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_type TEXT NOT NULL,
            status TEXT NOT NULL,
            bybit_side TEXT NOT NULL,
            hyperliquid_side TEXT NOT NULL,
            entry_bybit_price REAL NOT NULL,
            entry_hyperliquid_price REAL NOT NULL,
            target_notional_usd REAL NOT NULL,
            expected_net_bp REAL NOT NULL,
            expected_gross_bp REAL NOT NULL,
            total_cost_bp REAL NOT NULL,
            entry_spread_bp REAL,
            exit_bybit_price REAL,
            exit_hyperliquid_price REAL,
            closed_at TEXT,
            realized_pnl_usd REAL,
            realized_pnl_bp REAL,
            close_reason TEXT
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paper_trades_created_at ON paper_trades(created_at)"
    )

    connection.commit()

def get_connection(database_path: str) -> sqlite3.Connection:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: str) -> None:
    connection = get_connection(database_path)
    try:
        initialize_schema(connection)
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS heartbeat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                last_price REAL NOT NULL,
                mark_price REAL NOT NULL,
                index_price REAL,
                latency_ms REAL,
                orderbook_depth_usd REAL,
                observed_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                raw_rate REAL NOT NULL,
                interval_hours REAL NOT NULL,
                rate_8h_equivalent REAL NOT NULL,
                predicted_rate_8h_equivalent REAL,
                latency_ms REAL,
                observed_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                gross_expected_bp REAL NOT NULL,
                expected_net_bp REAL NOT NULL,
                total_cost_bp REAL NOT NULL,
                decision TEXT NOT NULL,
                reject_reason TEXT,
                bybit_value REAL NOT NULL,
                hyperliquid_value REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                status TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                reason TEXT NOT NULL,
                bybit_leg_status TEXT NOT NULL,
                hyperliquid_leg_status TEXT NOT NULL,
                notional_usd REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS position_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                bybit_side TEXT NOT NULL,
                hyperliquid_side TEXT NOT NULL,
                notional_usd REAL NOT NULL,
                entry_time TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_bybit_price REAL NOT NULL,
                entry_hyperliquid_price REAL NOT NULL,
                current_pnl REAL NOT NULL,
                expected_net_bp REAL NOT NULL,
                delta_imbalance_bp REAL DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                bybit_rate_8h REAL NOT NULL,
                hyperliquid_rate_8h REAL NOT NULL,
                normalized_diff_bp REAL NOT NULL,
                gross_expected_bp REAL DEFAULT 0,
                expected_net_bp REAL,
                long_exchange TEXT NOT NULL,
                short_exchange TEXT NOT NULL,
                meets_entry_threshold INTEGER NOT NULL,
                will_trade INTEGER DEFAULT 0,
                decision_reason TEXT DEFAULT '',
                observed_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scanner_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                decision_state TEXT NOT NULL,
                long_exchange TEXT NOT NULL,
                short_exchange TEXT NOT NULL,
                gross_expected_bp REAL NOT NULL,
                expected_net_bp REAL NOT NULL,
                threshold_bp REAL NOT NULL,
                reference_value_bp REAL NOT NULL,
                total_cost_bp REAL NOT NULL,
                will_trade INTEGER NOT NULL,
                decision_reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at TEXT NOT NULL,
                scanned_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                near_miss_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                open_paper_count INTEGER NOT NULL,
                best_symbol TEXT,
                best_strategy_type TEXT,
                best_gross_bp REAL,
                best_net_bp REAL,
                best_decision TEXT,
                best_reason TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS best_opportunity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_type TEXT,
                gross_bp REAL,
                net_bp REAL,
                decision TEXT,
                reason TEXT
            )
            """
        )
        _ensure_column(cursor, "position_pairs", "delta_imbalance_bp", "REAL DEFAULT 0")
        connection.commit()
    finally:
        connection.close()


def _ensure_column(
    cursor: sqlite3.Cursor,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

def insert_cycle_summary(
    db_path: str,
    scanned_count: int,
    accepted_count: int,
    near_miss_count: int,
    rejected_count: int,
    open_paper_count: int,
    best_symbol: str | None,
    best_strategy_type: str | None,
    best_gross_bp: float | None,
    best_net_bp: float | None,
    best_decision: str | None,
    best_reason: str | None,
) -> None:
    connection = get_connection(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO cycle_summaries (
                observed_at,
                scanned_count,
                accepted_count,
                near_miss_count,
                rejected_count,
                open_paper_count,
                best_symbol,
                best_strategy_type,
                best_gross_bp,
                best_net_bp,
                best_decision,
                best_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                scanned_count,
                accepted_count,
                near_miss_count,
                rejected_count,
                open_paper_count,
                best_symbol,
                best_strategy_type,
                best_gross_bp,
                best_net_bp,
                best_decision,
                best_reason,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def insert_best_opportunity_snapshot(
    db_path: str,
    symbol: str,
    strategy_type: str | None,
    gross_bp: float | None,
    net_bp: float | None,
    decision: str,
    reason: str | None,
) -> None:
    connection = get_connection(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO best_opportunity_snapshots (
                observed_at,
                symbol,
                strategy_type,
                gross_bp,
                net_bp,
                decision,
                reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                symbol,
                strategy_type,
                gross_bp,
                net_bp,
                decision,
                reason,
            ),
        )
        connection.commit()
    finally:
        connection.close()
