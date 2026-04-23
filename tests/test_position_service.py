from bot.execution.models import ExecutionIntent
from bot.position_manager.service import build_position_pair_from_intent


def test_build_position_pair_from_intent() -> None:
    intent = ExecutionIntent(
        symbol="ETHUSDT",
        long_exchange="hyperliquid",
        short_exchange="bybit",
        notional_usd=1500.0,
        strategy="funding_arbitrage",
    )

    position_pair = build_position_pair_from_intent(intent)

    assert position_pair.symbol == "ETHUSDT"
    assert position_pair.bybit_side == "Sell"
    assert position_pair.hyperliquid_side == "Buy"
    assert position_pair.notional_usd == 1500.0
    assert position_pair.status == "OPEN"