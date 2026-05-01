from __future__ import annotations
from bot.database.schema import get_connection

import sqlite3
from datetime import datetime


def _dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def insert_paper_trade(
    db_path: str,
    *,
    created_at: datetime,
    symbol: str,
    strategy_type: str,
    status: str,
    bybit_side: str,
    hyperliquid_side: str,
    entry_bybit_price: float,
    entry_hyperliquid_price: float,
    target_notional_usd: float,
    expected_net_bp: float,
    expected_gross_bp: float,
    total_cost_bp: float,
    entry_spread_bp: float | None,
) -> int:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO paper_trades (
                created_at,
                symbol,
                strategy_type,
                status,
                bybit_side,
                hyperliquid_side,
                entry_bybit_price,
                entry_hyperliquid_price,
                target_notional_usd,
                expected_net_bp,
                expected_gross_bp,
                total_cost_bp,
                entry_spread_bp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _dt_to_str(created_at),
                symbol,
                strategy_type,
                status,
                bybit_side,
                hyperliquid_side,
                entry_bybit_price,
                entry_hyperliquid_price,
                target_notional_usd,
                expected_net_bp,
                expected_gross_bp,
                total_cost_bp,
                entry_spread_bp,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_open_paper_trades(
    db_path: str,
    symbol: str | None = None,
    strategy_type: str | None = None,
) -> list[dict]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()

        query = """
            SELECT *
            FROM paper_trades
            WHERE status = 'OPEN'
        """
        params: list = []

        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)

        if strategy_type is not None:
            query += " AND strategy_type = ?"
            params.append(strategy_type)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def has_open_paper_trade(
    db_path: str,
    symbol: str,
    strategy_type: str,
) -> bool:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM paper_trades
            WHERE status = 'OPEN'
              AND symbol = ?
              AND strategy_type = ?
            LIMIT 1
            """,
            (symbol, strategy_type),
        )
        return cursor.fetchone() is not None
    finally:
        connection.close()


def close_paper_trade(
    db_path: str,
    trade_id: int,
    *,
    exit_bybit_price: float,
    exit_hyperliquid_price: float,
    realized_pnl_usd: float,
    realized_pnl_bp: float,
    close_reason: str,
    closed_at: datetime,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE paper_trades
            SET
                status = 'CLOSED',
                exit_bybit_price = ?,
                exit_hyperliquid_price = ?,
                realized_pnl_usd = ?,
                realized_pnl_bp = ?,
                close_reason = ?,
                closed_at = ?
            WHERE id = ?
            """,
            (
                exit_bybit_price,
                exit_hyperliquid_price,
                realized_pnl_usd,
                realized_pnl_bp,
                close_reason,
                _dt_to_str(closed_at),
                trade_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

def get_paper_trade_summary(db_path: str) -> dict:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) AS count FROM paper_trades")
        total_trades = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM paper_trades WHERE status = 'OPEN'")
        open_trades = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM paper_trades WHERE status = 'CLOSED'")
        closed_trades = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(realized_pnl_usd), 0.0) AS total_realized_pnl_usd,
                COALESCE(SUM(target_notional_usd), 0.0) AS total_closed_notional_usd
            FROM paper_trades
            WHERE status = 'CLOSED'
            """
        )
        pnl_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_trades
            WHERE status = 'CLOSED' AND realized_pnl_usd > 0
            """
        )
        winners = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_trades
            WHERE status = 'CLOSED' AND realized_pnl_usd <= 0
            """
        )
        losers = cursor.fetchone()["count"]

        win_rate = (winners / closed_trades * 100.0) if closed_trades else 0.0

        return {
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "winners": winners,
            "losers": losers,
            "win_rate_pct": win_rate,
            "total_realized_pnl_usd": pnl_row["total_realized_pnl_usd"],
            "aggregate_realized_pnl_bp": (
                (pnl_row["total_realized_pnl_usd"] / pnl_row["total_closed_notional_usd"]) * 10_000
                if pnl_row["total_closed_notional_usd"]
                else 0.0
            ),
        }
    finally:
        connection.close()

def list_paper_trades(db_path: str) -> list[dict[str, object]]:
    connection = get_connection(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                created_at,
                symbol,
                strategy_type,
                status,
                bybit_side,
                hyperliquid_side,
                entry_bybit_price,
                entry_hyperliquid_price,
                target_notional_usd,
                expected_net_bp,
                expected_gross_bp,
                total_cost_bp,
                entry_spread_bp,
                exit_bybit_price,
                exit_hyperliquid_price,
                closed_at,
                realized_pnl_usd,
                realized_pnl_bp,
                close_reason
            FROM paper_trades
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
