import asyncio

from bot.execution.models import ExecutionIntent
from bot.execution.router import submit_execution_intent


def test_submit_execution_intent_returns_accepted_result() -> None:
    intent = ExecutionIntent(
        symbol="BTCUSDT",
        long_exchange="bybit",
        short_exchange="hyperliquid",
        notional_usd=2000.0,
        strategy="funding_arbitrage",
    )

    result = asyncio.run(submit_execution_intent(intent))

    assert result.accepted is True
    assert result.status == "ACCEPTED"
    assert result.symbol == "BTCUSDT"
