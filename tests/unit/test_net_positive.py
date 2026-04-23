from __future__ import annotations

from datetime import datetime, timezone

from bot.config.config import load_config
from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.risk_engine.net_positive import pre_trade_net_positive_check
from bot.signal_generator.funding_strategy import build_funding_snapshot, calculate_funding_diff_bp
from bot.signal_generator.spread_strategy import build_spread_snapshot, estimate_convergence_capture_bp


def _load_test_config(monkeypatch):
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")
    return load_config()


def test_rejects_when_expected_net_is_below_minimum(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    result = pre_trade_net_positive_check("BTCUSDT", "funding_arbitrage", 10.0, config)
    assert result.passed is False
    assert result.reject_reason is not None


def test_passes_when_expected_net_is_positive(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    result = pre_trade_net_positive_check("BTCUSDT", "funding_arbitrage", 30.0, config)
    assert result.passed is True
    assert result.expected_net_bp > config.min_net_expected_return_bp


def test_uses_dynamic_fee_when_available(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    monkeypatch.setenv("CURRENT_BYBIT_MAKER_FEE_BP", "4.0")
    monkeypatch.setenv("CURRENT_HYPERLIQUID_MAKER_FEE_BP", "3.0")
    result = pre_trade_net_positive_check("BTCUSDT", "funding_arbitrage", 30.0, config)
    assert result.bybit_fee_bp == 4.0
    assert result.hyperliquid_fee_bp == 3.0


def test_falls_back_to_config_fee_when_dynamic_fee_unavailable(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    monkeypatch.delenv("CURRENT_BYBIT_MAKER_FEE_BP", raising=False)
    monkeypatch.delenv("CURRENT_HYPERLIQUID_MAKER_FEE_BP", raising=False)
    result = pre_trade_net_positive_check("BTCUSDT", "funding_arbitrage", 30.0, config)
    assert result.bybit_fee_bp == config.bybit_maker_fee_bp
    assert result.hyperliquid_fee_bp == config.hyperliquid_maker_fee_bp


def test_funding_strategy_gross_calc_is_based_on_normalized_diff(monkeypatch) -> None:
    _load_test_config(monkeypatch)
    bybit = FundingRateSnapshot(
        exchange="bybit",
        symbol="BTCUSDT",
        raw_rate=0.0001,
        interval_hours=8.0,
        rate_8h_equivalent=0.0001,
        observed_at=datetime.now(timezone.utc),
    )
    hyperliquid = FundingRateSnapshot(
        exchange="hyperliquid",
        symbol="BTCUSDT",
        raw_rate=0.0004,
        interval_hours=1.0,
        rate_8h_equivalent=0.0032,
        observed_at=datetime.now(timezone.utc),
    )
    snapshot = build_funding_snapshot(bybit, hyperliquid)
    assert round(abs(calculate_funding_diff_bp(snapshot)), 2) == 31.0


def test_spread_strategy_gross_calc_applies_expected_convergence(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    snapshot = build_spread_snapshot("BTCUSDT", bybit_price=100.0, hyperliquid_price=101.0)
    gross_expected_bp = estimate_convergence_capture_bp(
        snapshot.spread_bp,
        config.expected_convergence_pct,
    )
    assert round(gross_expected_bp, 2) == round(abs(snapshot.spread_bp) * 0.85, 2)
