from bot.signal_generator.market_data_sanity import check_cross_exchange_price_sanity


def test_cross_exchange_price_sanity_passes_for_small_gap() -> None:
    result = check_cross_exchange_price_sanity(100.0, 100.5, max_relative_diff=0.02)
    assert result.sane is True


def test_cross_exchange_price_sanity_fails_for_large_gap() -> None:
    result = check_cross_exchange_price_sanity(100.0, 120.0, max_relative_diff=0.05)
    assert result.sane is False
