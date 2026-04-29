from __future__ import annotations

import sqlite3
from typing import Any


def _fetch_all(db_path: str, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def get_cycle_summary_stats(db_path: str, limit: int = 100) -> dict[str, Any]:
    rows = _fetch_all(
        db_path,
        """
        SELECT *
        FROM cycle_summaries
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    if not rows:
        return {
            "cycles": 0,
            "avg_scanned": 0.0,
            "avg_accepted": 0.0,
            "avg_near_miss": 0.0,
            "avg_rejected": 0.0,
            "avg_open_paper": 0.0,
            "avg_best_net_bp": 0.0,
        }

    count = len(rows)
    return {
        "cycles": count,
        "avg_scanned": sum(r["scanned_count"] for r in rows) / count,
        "avg_accepted": sum(r["accepted_count"] for r in rows) / count,
        "avg_near_miss": sum(r["near_miss_count"] for r in rows) / count,
        "avg_rejected": sum(r["rejected_count"] for r in rows) / count,
        "avg_open_paper": sum(r["open_paper_count"] for r in rows) / count,
        "avg_best_net_bp": sum((r["best_net_bp"] or 0.0) for r in rows) / count,
    }


def get_best_symbol_breakdown(db_path: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetch_all(
        db_path,
        """
        SELECT
            best_symbol,
            best_strategy_type,
            COUNT(*) AS frequency,
            AVG(best_gross_bp) AS avg_gross_bp,
            AVG(best_net_bp) AS avg_net_bp
        FROM cycle_summaries
        WHERE best_symbol IS NOT NULL
        GROUP BY best_symbol, best_strategy_type
        ORDER BY frequency DESC, avg_net_bp DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


def get_near_miss_breakdown(db_path: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetch_all(
        db_path,
        """
        SELECT
            symbol,
            strategy_type,
            COUNT(*) AS near_miss_count,
            AVG(gross_bp) AS avg_gross_bp,
            AVG(net_bp) AS avg_net_bp,
            MAX(net_bp) AS best_net_bp
        FROM best_opportunity_snapshots
        WHERE decision = 'near_miss'
        GROUP BY symbol, strategy_type
        ORDER BY best_net_bp DESC, near_miss_count DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


def get_latest_paper_summary_row(db_path: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS opened FROM paper_trades")
        opened = cur.fetchone()["opened"]

        cur.execute("SELECT COUNT(*) AS closed FROM paper_trades WHERE status = 'CLOSED'")
        closed = cur.fetchone()["closed"]

        cur.execute("SELECT COUNT(*) AS open_count FROM paper_trades WHERE status = 'OPEN'")
        open_count = cur.fetchone()["open_count"]

        cur.execute(
            """
            SELECT
                COALESCE(SUM(realized_pnl_usd), 0.0) AS realized_pnl_usd,
                COALESCE(AVG(realized_pnl_bp), 0.0) AS avg_realized_pnl_bp
            FROM paper_trades
            WHERE status = 'CLOSED'
            """
        )
        pnl_row = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*) AS wins
            FROM paper_trades
            WHERE status = 'CLOSED' AND COALESCE(realized_pnl_usd, 0.0) > 0
            """
        )
        wins = cur.fetchone()["wins"]

        win_rate = (wins / closed) if closed else 0.0

        cur.execute(
            """
            SELECT AVG(
                (julianday(closed_at) - julianday(created_at)) * 24 * 60
            ) AS avg_hold_mins
            FROM paper_trades
            WHERE status = 'CLOSED' AND closed_at IS NOT NULL
            """
        )
        avg_hold_row = cur.fetchone()

        return {
            "opened": opened,
            "closed": closed,
            "open_count": open_count,
            "realized_pnl_usd": pnl_row["realized_pnl_usd"] or 0.0,
            "avg_realized_pnl_bp": pnl_row["avg_realized_pnl_bp"] or 0.0,
            "win_rate": win_rate,
            "avg_hold_mins": avg_hold_row["avg_hold_mins"] or 0.0,
        }
    finally:
        conn.close()
