from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.config.config import load_config
from bot.risk_engine.checks import run_pre_trade_risk_checks
from bot.risk_engine.market_state import MarketStateTracker
from bot.signal_generator.models import TradeIntent


@dataclass(frozen=True)
class DummyAccountState:
    margin_utilization: float
    margin_ratio_pct: float = 200.0


def _load_test_config(monkeypatch):
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")
    return load_config()


def _build_intent(notional: float = 2_000.0) -> TradeIntent:
    return TradeIntent(
        symbol="BTCUSDT",
        strategy_type="funding_arbitrage",
        bybit_side="Buy",
        hyperliquid_side="Sell",
        target_notional_usd=notional,
        gross_expected_bp=25.0,
        expected_net_bp=5.0,
        created_at=datetime.now(timezone.utc),
    )


def _build_market_state() -> MarketStateTracker:
    tracker = MarketStateTracker()
    now = datetime.now(timezone.utc)
    tracker.record_price("bybit", "BTCUSDT", 100.0, now - timedelta(seconds=30))
    tracker.record_price("bybit", "BTCUSDT", 100.5, now)
    tracker.record_price("hyperliquid", "BTCUSDT", 100.0, now - timedelta(seconds=30))
    tracker.record_price("hyperliquid", "BTCUSDT", 100.4, now)
    tracker.record_depth("bybit", "BTCUSDT", 1_000_000.0, now)
    tracker.record_depth("hyperliquid", "BTCUSDT", 1_000_000.0, now)
    return tracker


def test_margin_cap_rejection(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    result = run_pre_trade_risk_checks(
        _build_intent(),
        DummyAccountState(margin_utilization=0.50),
        _build_market_state(),
        config,
        {"bybit": {"latency_ms": 100.0}, "hyperliquid": {"latency_ms": 100.0}},
    )
    assert result.passed is False
    assert any("Margin utilization" in reason for reason in result.reasons)


def test_liquidity_rejection(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    tracker = MarketStateTracker()
    now = datetime.now(timezone.utc)
    tracker.record_depth("bybit", "BTCUSDT", 100_000.0, now)
    tracker.record_depth("hyperliquid", "BTCUSDT", 100_000.0, now)
    tracker.record_price("bybit", "BTCUSDT", 100.0, now)
    tracker.record_price("hyperliquid", "BTCUSDT", 100.0, now)
    result = run_pre_trade_risk_checks(
        _build_intent(notional=2_000.0),
        DummyAccountState(margin_utilization=0.10),
        tracker,
        config,
        {"bybit": {"latency_ms": 100.0}, "hyperliquid": {"latency_ms": 100.0}},
    )
    assert result.passed is False
    assert any("Liquidity cap" in reason for reason in result.reasons)


def test_latency_rejection(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    result = run_pre_trade_risk_checks(
        _build_intent(),
        DummyAccountState(margin_utilization=0.10),
        _build_market_state(),
        config,
        {"bybit": {"latency_ms": 600.0}, "hyperliquid": {"latency_ms": 100.0}},
    )
    assert result.passed is False
    assert any("latency" in reason.lower() for reason in result.reasons)


def test_oversized_notional_rejection(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)
    result = run_pre_trade_risk_checks(
        _build_intent(notional=20_000.0),
        DummyAccountState(margin_utilization=0.10),
        _build_market_state(),
        config,
        {"bybit": {"latency_ms": 100.0}, "hyperliquid": {"latency_ms": 100.0}},
    )
    assert result.passed is False
    assert any("max per-pair limit" in reason for reason in result.reasons)
