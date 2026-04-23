from bot.config.config import load_settings
from bot.signal_generator.decisioning import build_strategy_decision


def test_build_strategy_decision_marks_near_miss(monkeypatch) -> None:
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")

    settings = load_settings()
    decision = build_strategy_decision(
        strategy_type="funding_arbitrage",
        symbol="BTCUSDT",
        gross_expected_bp=14.0,
        threshold_bp=16.0,
        reference_value_bp=14.0,
        long_exchange="bybit",
        short_exchange="hyperliquid",
        settings=settings,
        risk_blockers=[],
    )

    assert decision is not None
    assert decision.event_type == "near_miss"
    assert decision.will_trade is False
