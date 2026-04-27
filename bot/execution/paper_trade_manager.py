from __future__ import annotations

from datetime import datetime, timezone

from bot.analytics.pnl import (
    age_minutes,
    compute_spread_bp,
    compute_spread_convergence_pnl_usd,
    pnl_usd_to_bp,
)
from bot.database.paper_trade_repository import get_open_paper_trades, close_paper_trade


async def reconcile_open_paper_trades(
    db_path: str,
    latest_prices: dict[str, dict[str, float]],
    max_hold_minutes: int,
) -> int:
    now = datetime.now(timezone.utc)
    open_trades = get_open_paper_trades(db_path)
    closed_count = 0

    for trade in open_trades:
        symbol = trade["symbol"]
        strategy_type = trade["strategy_type"]

        if symbol not in latest_prices:
            continue

        bybit_price = latest_prices[symbol].get("bybit_price")
        hyperliquid_price = latest_prices[symbol].get("hyperliquid_price")

        if not bybit_price or not hyperliquid_price:
            continue

        should_close = False
        close_reason = "timeout"

        current_spread_bp = compute_spread_bp(bybit_price, hyperliquid_price)
        opened_minutes = age_minutes(trade["created_at"], now)

        if strategy_type == "spread_convergence":
            entry_spread_bp = trade["entry_spread_bp"] or 0.0
            if abs(current_spread_bp) < abs(entry_spread_bp) * 0.25:
                should_close = True
                close_reason = "spread_converged"
            elif opened_minutes >= max_hold_minutes:
                should_close = True
                close_reason = "max_hold_timeout"

        elif strategy_type == "funding_arbitrage":
            if opened_minutes >= max_hold_minutes:
                should_close = True
                close_reason = "funding_hold_timeout"

        if not should_close:
            continue

        realized_pnl_usd = compute_spread_convergence_pnl_usd(
            entry_bybit_price=float(trade["entry_bybit_price"]),
            entry_hyperliquid_price=float(trade["entry_hyperliquid_price"]),
            exit_bybit_price=float(bybit_price),
            exit_hyperliquid_price=float(hyperliquid_price),
            notional_usd=float(trade["target_notional_usd"]),
            bybit_side=str(trade["bybit_side"]),
            hyperliquid_side=str(trade["hyperliquid_side"]),
        )
        realized_pnl_bp = pnl_usd_to_bp(
            realized_pnl_usd=realized_pnl_usd,
            notional_usd=float(trade["target_notional_usd"]),
        )

        close_paper_trade(
            db_path=db_path,
            trade_id=int(trade["id"]),
            exit_bybit_price=float(bybit_price),
            exit_hyperliquid_price=float(hyperliquid_price),
            realized_pnl_usd=realized_pnl_usd,
            realized_pnl_bp=realized_pnl_bp,
            close_reason=close_reason,
            closed_at=now,
        )
        closed_count += 1

    return closed_count
