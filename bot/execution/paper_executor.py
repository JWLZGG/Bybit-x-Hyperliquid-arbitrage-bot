from __future__ import annotations

from datetime import datetime, timezone

from bot.analytics.pnl import compute_spread_bp
from bot.database.paper_trade_repository import insert_paper_trade, has_open_paper_trade
from bot.execution.models import ExecutionResult, LegExecutionResult
from bot.signal_generator.models import TradeIntent


async def execute_paper_pair(
    intent: TradeIntent,
    bybit_price: float,
    hyperliquid_price: float,
    db_path: str,
    total_cost_bp: float,
) -> ExecutionResult:
    now = datetime.now(timezone.utc)

    if has_open_paper_trade(
        db_path=db_path,
        symbol=intent.symbol,
        strategy_type=intent.strategy_type,
    ):
        return ExecutionResult(
            symbol=intent.symbol,
            strategy_type=intent.strategy_type,
            status="PAPER_SKIPPED_DUPLICATE",
            accepted=False,
            reason="Skipped paper trade because an OPEN trade already exists for this symbol and strategy",
            bybit_leg=LegExecutionResult(
                exchange="bybit",
                side=intent.bybit_side,
                order_id="",
                requested_notional_usd=intent.target_notional_usd,
                filled_notional_usd=0.0,
                average_fill_price=bybit_price,
                status="SKIPPED",
                reason="Open paper trade already exists",
            ),
            hyperliquid_leg=LegExecutionResult(
                exchange="hyperliquid",
                side=intent.hyperliquid_side,
                order_id="",
                requested_notional_usd=intent.target_notional_usd,
                filled_notional_usd=0.0,
                average_fill_price=hyperliquid_price,
                status="SKIPPED",
                reason="Open paper trade already exists",
            ),
            created_at=now,
            metadata={
                "mode": "paper",
                "duplicate_open_trade": True,
            },
        )

    entry_spread_bp = compute_spread_bp(bybit_price, hyperliquid_price)

    trade_id = insert_paper_trade(
        db_path,
        created_at=now,
        symbol=intent.symbol,
        strategy_type=intent.strategy_type,
        status="OPEN",
        bybit_side=intent.bybit_side,
        hyperliquid_side=intent.hyperliquid_side,
        entry_bybit_price=bybit_price,
        entry_hyperliquid_price=hyperliquid_price,
        target_notional_usd=intent.target_notional_usd,
        expected_net_bp=float(intent.expected_net_bp),
        expected_gross_bp=float(intent.gross_expected_bp),
        total_cost_bp=float(total_cost_bp),
        entry_spread_bp=entry_spread_bp,
    )

    return ExecutionResult(
        symbol=intent.symbol,
        strategy_type=intent.strategy_type,
        status="PAPER_OPEN",
        accepted=True,
        reason=f"Paper trade opened (id={trade_id})",
        bybit_leg=LegExecutionResult(
            exchange="bybit",
            side=intent.bybit_side,
            order_id=f"paper-bybit-{trade_id}",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=intent.target_notional_usd,
            average_fill_price=bybit_price,
            status="OPEN",
            reason="Paper execution",
        ),
        hyperliquid_leg=LegExecutionResult(
            exchange="hyperliquid",
            side=intent.hyperliquid_side,
            order_id=f"paper-hyperliquid-{trade_id}",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=intent.target_notional_usd,
            average_fill_price=hyperliquid_price,
            status="OPEN",
            reason="Paper execution",
        ),
        created_at=now,
        metadata={
            "paper_trade_id": trade_id,
            "entry_bybit_price": bybit_price,
            "entry_hyperliquid_price": hyperliquid_price,
            "entry_spread_bp": entry_spread_bp,
            "mode": "paper",
        },
    )
