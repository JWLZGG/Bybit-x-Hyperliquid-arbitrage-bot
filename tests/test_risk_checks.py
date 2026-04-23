from bot.risk_engine.checks import (
    check_global_margin_utilization,
    check_latency_guard,
    check_liquidity_depth,
    check_margin_ratio,
    check_one_minute_volatility,
    check_per_pair_notional,
)


def test_check_global_margin_utilization_passes() -> None:
    result = check_global_margin_utilization(0.20)
    assert result.allowed is True


def test_check_global_margin_utilization_fails() -> None:
    result = check_global_margin_utilization(0.40)
    assert result.allowed is False


def test_check_per_pair_notional_fails() -> None:
    result = check_per_pair_notional(6000.0, max_notional_usd=5000.0)
    assert result.allowed is False


def test_check_per_pair_notional_rejects_zero() -> None:
    result = check_per_pair_notional(0.0, max_notional_usd=5000.0)
    assert result.allowed is False


def test_check_latency_guard_fails() -> None:
    result = check_latency_guard(750.0, max_latency_ms=500.0)
    assert result.allowed is False


def test_check_margin_ratio_fails() -> None:
    result = check_margin_ratio(120.0, min_margin_ratio_pct=150.0)
    assert result.allowed is False


def test_check_one_minute_volatility_passes_without_history() -> None:
    result = check_one_minute_volatility(None, max_one_minute_move_pct=2.0)
    assert result.allowed is True


def test_check_liquidity_depth_fails_when_notional_too_large() -> None:
    result = check_liquidity_depth(
        proposed_notional_usd=1000.0,
        average_depth_usd=100_000.0,
        max_depth_fraction=0.005,
    )
    assert result.allowed is False
