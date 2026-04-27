from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


def compute_spread_bp(bybit_price: float, hyperliquid_price: float) -> float:
    mid = (bybit_price + hyperliquid_price) / 2
    if mid <= 0:
        return 0.0
    return ((hyperliquid_price - bybit_price) / mid) * 10_000


def compute_spread_convergence_pnl_usd(
    entry_bybit_price: float,
    entry_hyperliquid_price: float,
    exit_bybit_price: float,
    exit_hyperliquid_price: float,
    notional_usd: float,
    bybit_side: str,
    hyperliquid_side: str,
) -> float:
    if entry_bybit_price <= 0 or entry_hyperliquid_price <= 0:
        return 0.0

    bybit_qty = notional_usd / entry_bybit_price
    hyperliquid_qty = notional_usd / entry_hyperliquid_price

    bybit_pnl = (
        (exit_bybit_price - entry_bybit_price) * bybit_qty
        if bybit_side.lower() == "buy"
        else (entry_bybit_price - exit_bybit_price) * bybit_qty
    )

    hyperliquid_pnl = (
        (exit_hyperliquid_price - entry_hyperliquid_price) * hyperliquid_qty
        if hyperliquid_side.lower() == "buy"
        else (entry_hyperliquid_price - exit_hyperliquid_price) * hyperliquid_qty
    )

    return bybit_pnl + hyperliquid_pnl


def pnl_usd_to_bp(realized_pnl_usd: float, notional_usd: float) -> float:
    if notional_usd <= 0:
        return 0.0
    return (realized_pnl_usd / notional_usd) * 10_000


def age_minutes(created_at_iso: str, now: datetime) -> float:
    created = datetime.fromisoformat(created_at_iso)
    return (now - created).total_seconds() / 60.0


def compute_paper_trade_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    opened = len(rows)
    open_rows = [row for row in rows if row.get("status") == "OPEN"]
    closed_rows = [row for row in rows if row.get("status") == "CLOSED"]

    realized_pnl_usd = sum(float(row.get("realized_pnl_usd") or 0.0) for row in closed_rows)
    realized_notional_usd = sum(float(row.get("target_notional_usd") or 0.0) for row in closed_rows)
    realized_pnl_bp = pnl_usd_to_bp(realized_pnl_usd, realized_notional_usd) if realized_notional_usd > 0 else 0.0

    wins = sum(1 for row in closed_rows if float(row.get("realized_pnl_usd") or 0.0) > 0)
    win_rate = (wins / len(closed_rows)) if closed_rows else 0.0

    holding_minutes_total = 0.0
    holding_minutes_count = 0
    for row in closed_rows:
        created_at = row.get("created_at")
        closed_at = row.get("closed_at")
        if created_at and closed_at:
            try:
                created = datetime.fromisoformat(created_at)
                closed = datetime.fromisoformat(closed_at)
                holding_minutes_total += (closed - created).total_seconds() / 60.0
                holding_minutes_count += 1
            except ValueError:
                pass

    average_holding_minutes = (
        holding_minutes_total / holding_minutes_count if holding_minutes_count else 0.0
    )

    by_symbol: dict[str, dict[str, float]] = defaultdict(lambda: {
        "opened": 0,
        "closed": 0,
        "open": 0,
        "realized_pnl_usd": 0.0,
    })
    by_strategy: dict[str, dict[str, float]] = defaultdict(lambda: {
        "opened": 0,
        "closed": 0,
        "open": 0,
        "realized_pnl_usd": 0.0,
    })

    for row in rows:
        symbol = str(row.get("symbol") or "UNKNOWN")
        strategy = str(row.get("strategy_type") or "UNKNOWN")
        status = str(row.get("status") or "UNKNOWN")
        pnl = float(row.get("realized_pnl_usd") or 0.0)

        by_symbol[symbol]["opened"] += 1
        by_strategy[strategy]["opened"] += 1

        if status == "OPEN":
            by_symbol[symbol]["open"] += 1
            by_strategy[strategy]["open"] += 1
        elif status == "CLOSED":
            by_symbol[symbol]["closed"] += 1
            by_strategy[strategy]["closed"] += 1
            by_symbol[symbol]["realized_pnl_usd"] += pnl
            by_strategy[strategy]["realized_pnl_usd"] += pnl

    return {
        "opened": opened,
        "closed": len(closed_rows),
        "open_count": len(open_rows),
        "realized_pnl_usd": realized_pnl_usd,
        "realized_pnl_bp": realized_pnl_bp,
        "win_rate": win_rate,
        "average_holding_minutes": average_holding_minutes,
        "by_symbol": dict(by_symbol),
        "by_strategy": dict(by_strategy),
    }
