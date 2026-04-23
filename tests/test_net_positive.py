from bot.config.config import load_settings
from bot.risk_engine.net_positive import evaluate_pre_trade_net_positive_check


def test_net_positive_check_passes_with_large_edge(monkeypatch) -> None:
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")

    settings = load_settings()
    result = evaluate_pre_trade_net_positive_check(
        symbol="BTCUSDT",
        strategy_type="funding_arbitrage",
        gross_expected_bp=25.0,
        settings=settings,
    )

    assert result.passed is True
    assert result.expected_net_bp > settings.min_net_expected_return_bp


def test_net_positive_check_fails_when_costs_dominate(monkeypatch) -> None:
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")

    settings = load_settings()
    result = evaluate_pre_trade_net_positive_check(
        symbol="BTCUSDT",
        strategy_type="funding_arbitrage",
        gross_expected_bp=10.0,
        settings=settings,
    )

    assert result.passed is False
    assert "No net-positive opportunity" in result.reason
