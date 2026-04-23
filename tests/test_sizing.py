from bot.risk_engine.sizing import calculate_safe_notional


def test_calculate_safe_notional_under_cap() -> None:
    assert (
        calculate_safe_notional(
            available_capital_usd=10000.0,
            current_margin_utilization=0.10,
            max_margin_utilization=0.30,
            max_notional_usd=5000.0,
        )
        == 2000.0
    )


def test_calculate_safe_notional_hits_cap() -> None:
    assert (
        calculate_safe_notional(
            available_capital_usd=100000.0,
            current_margin_utilization=0.00,
            max_margin_utilization=0.30,
            max_notional_usd=5000.0,
        )
        == 5000.0
    )
