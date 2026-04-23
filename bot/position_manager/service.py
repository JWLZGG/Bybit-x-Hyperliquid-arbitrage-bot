from __future__ import annotations

from bot.execution.models import ExecutionIntent, ExecutionResult, PositionPair
from bot.signal_generator.models import TradeIntent


def build_position_pair_from_intent(intent: TradeIntent | ExecutionIntent) -> PositionPair:
    trade_intent = intent if isinstance(intent, TradeIntent) else intent.to_trade_intent()
    return PositionPair(
        symbol=trade_intent.symbol,
        strategy_type=trade_intent.strategy_type,
        bybit_side=trade_intent.bybit_side,
        hyperliquid_side=trade_intent.hyperliquid_side,
        notional_usd=trade_intent.target_notional_usd,
        entry_time=trade_intent.created_at,
        status="OPEN",
        entry_bybit_price=float(trade_intent.metadata.get("bybit_price", 0.0)),
        entry_hyperliquid_price=float(trade_intent.metadata.get("hyperliquid_price", 0.0)),
        current_pnl=0.0,
        expected_net_bp=trade_intent.expected_net_bp,
    )


def build_position_pair_from_execution(
    intent: TradeIntent,
    execution_result: ExecutionResult,
) -> PositionPair:
    return PositionPair(
        symbol=intent.symbol,
        strategy_type=intent.strategy_type,
        bybit_side=intent.bybit_side,
        hyperliquid_side=intent.hyperliquid_side,
        notional_usd=execution_result.notional_usd,
        entry_time=execution_result.created_at,
        status="OPEN" if execution_result.accepted else "FAILED",
        entry_bybit_price=execution_result.bybit_leg.average_fill_price,
        entry_hyperliquid_price=execution_result.hyperliquid_leg.average_fill_price,
        current_pnl=0.0,
        expected_net_bp=intent.expected_net_bp,
    )
