from datetime import datetime, timezone

from bot.execution.canary_guard import validate_canary_intent
from bot.signal_generator.models import TradeIntent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_intent(symbol: str, expected_net_bp: float, gross_expected_bp: float) -> TradeIntent:
    return TradeIntent(
        created_at=now_iso(),
        symbol=symbol,
        strategy_type="price_spread_convergence",
        bybit_side="BUY",
        hyperliquid_side="SELL",
        target_notional_usd=2.0,
        expected_net_bp=expected_net_bp,
        gross_expected_bp=gross_expected_bp,
    )


def main():
    below_threshold = make_intent(
        symbol="DYDXUSDT",
        expected_net_bp=5.0,
        gross_expected_bp=16.0,
    )

    ok, reason, checked_intent = validate_canary_intent(below_threshold)

    print("below_threshold_ok=", ok)
    print("below_threshold_reason=", reason)
    print("symbol=", checked_intent.symbol)
    print("expected_net_bp=", checked_intent.expected_net_bp)
    print("---")

    above_threshold = make_intent(
        symbol="DYDXUSDT",
        expected_net_bp=11.0,
        gross_expected_bp=22.0,
    )

    ok, reason, checked_intent = validate_canary_intent(above_threshold)

    print("above_threshold_ok=", ok)
    print("above_threshold_reason=", reason)
    print("symbol=", checked_intent.symbol)
    print("expected_net_bp=", checked_intent.expected_net_bp)


if __name__ == "__main__":
    main()
