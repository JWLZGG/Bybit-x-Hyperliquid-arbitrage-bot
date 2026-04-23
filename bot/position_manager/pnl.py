from __future__ import annotations

from bot.execution.models import PositionPair


def calculate_unrealized_pnl(
    position_pair: PositionPair,
    current_bybit_price: float,
    current_hyperliquid_price: float,
) -> float:
    bybit_direction = 1 if position_pair.bybit_side.lower() == "buy" else -1
    hyperliquid_direction = 1 if position_pair.hyperliquid_side.lower() == "buy" else -1

    bybit_qty = position_pair.notional_usd / max(position_pair.entry_bybit_price, 1.0)
    hyperliquid_qty = position_pair.notional_usd / max(position_pair.entry_hyperliquid_price, 1.0)

    bybit_pnl = (current_bybit_price - position_pair.entry_bybit_price) * bybit_qty * bybit_direction
    hyperliquid_pnl = (
        (current_hyperliquid_price - position_pair.entry_hyperliquid_price)
        * hyperliquid_qty
        * hyperliquid_direction
    )
    return bybit_pnl + hyperliquid_pnl


def calculate_realized_pnl(
    entry_notional_usd: float,
    exit_notional_usd: float,
    trading_cost_usd: float = 0.0,
) -> float:
    return exit_notional_usd - entry_notional_usd - trading_cost_usd


def calculate_funding_pnl_component(
    notional_usd: float,
    funding_diff_rate: float,
) -> float:
    return notional_usd * funding_diff_rate


def calculate_spread_capture_component(
    notional_usd: float,
    captured_spread_bp: float,
) -> float:
    return notional_usd * (captured_spread_bp / 10_000)
