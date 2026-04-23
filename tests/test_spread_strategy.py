from bot.signal_generator.spread_strategy import build_spread_signal


def test_build_spread_signal_longs_cheaper_exchange() -> None:
    signal = build_spread_signal(
        symbol="BTCUSDT",
        bybit_price=100.0,
        hyperliquid_price=101.0,
        entry_threshold_bp=16.0,
        expected_convergence_pct=85.0,
    )

    assert signal.long_exchange == "bybit"
    assert signal.short_exchange == "hyperliquid"
    assert signal.meets_entry_threshold is True
    assert signal.gross_expected_bp > 0
