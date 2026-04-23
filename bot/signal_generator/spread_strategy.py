from __future__ import annotations

from datetime import datetime, timezone

from bot.config.config import Config
from bot.risk_engine.net_positive import NetPositiveResult, pre_trade_net_positive_check
from bot.signal_generator.models import Opportunity, SpreadSnapshot, TradeIntent
from bot.signal_generator.spread_signal import SpreadSignal


def calculate_spread_bp(bybit_price: float, hyperliquid_price: float) -> float:
    midpoint = (bybit_price + hyperliquid_price) / 2
    return ((hyperliquid_price - bybit_price) / midpoint) * 10_000


def estimate_convergence_capture_bp(
    spread_bp: float,
    expected_convergence_pct: float,
) -> float:
    return abs(spread_bp) * (expected_convergence_pct / 100)


def build_spread_snapshot(
    symbol: str,
    bybit_price: float,
    hyperliquid_price: float,
    timestamp: datetime | None = None,
) -> SpreadSnapshot:
    if bybit_price <= 0 or hyperliquid_price <= 0:
        raise ValueError("Spread prices must be positive")
    return SpreadSnapshot(
        symbol=symbol,
        bybit_price=bybit_price,
        hyperliquid_price=hyperliquid_price,
        spread_bp=calculate_spread_bp(bybit_price, hyperliquid_price),
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def _determine_pair_sides(snapshot: SpreadSnapshot) -> tuple[str, str]:
    if snapshot.bybit_price <= snapshot.hyperliquid_price:
        return "Buy", "Sell"
    return "Sell", "Buy"


def evaluate_spread_opportunity(
    snapshot: SpreadSnapshot,
    config: Config,
) -> tuple[Opportunity, NetPositiveResult]:
    gross_expected_bp = estimate_convergence_capture_bp(
        snapshot.spread_bp,
        config.expected_convergence_pct,
    )
    net_positive_result = pre_trade_net_positive_check(
        symbol=snapshot.symbol,
        strategy_type="price_spread_convergence",
        gross_expected_bp=gross_expected_bp,
        config=config,
    )
    threshold_bp = config.spread_threshold_bp

    if abs(snapshot.spread_bp) >= threshold_bp and net_positive_result.passed:
        decision = "accepted"
        reject_reason = None
    elif abs(snapshot.spread_bp) >= threshold_bp:
        decision = "rejected_net_positive"
        reject_reason = net_positive_result.reject_reason
    elif abs(snapshot.spread_bp) >= threshold_bp * config.near_miss_threshold_ratio:
        decision = "near_miss"
        reject_reason = "Spread below entry threshold"
    else:
        decision = "near_miss"
        reject_reason = "Spread below near-miss threshold"

    opportunity = Opportunity(
        timestamp=snapshot.timestamp,
        symbol=snapshot.symbol,
        strategy_type="price_spread_convergence",
        gross_expected_bp=gross_expected_bp,
        expected_net_bp=net_positive_result.expected_net_bp,
        total_cost_bp=net_positive_result.total_cost_bp,
        decision=decision,
        reject_reason=reject_reason,
        bybit_value=snapshot.bybit_price,
        hyperliquid_value=snapshot.hyperliquid_price,
        metadata={
            "spread_bp": snapshot.spread_bp,
            "expected_convergence_pct": config.expected_convergence_pct,
            "max_hold_minutes": config.max_hold_minutes,
        },
    )
    return opportunity, net_positive_result


def maybe_emit_trade_intent(
    snapshot: SpreadSnapshot,
    config: Config,
    target_notional_usd: float,
) -> tuple[Opportunity, TradeIntent | None]:
    opportunity, net_positive_result = evaluate_spread_opportunity(snapshot, config)
    if opportunity.decision != "accepted":
        return opportunity, None

    bybit_side, hyperliquid_side = _determine_pair_sides(snapshot)
    trade_intent = TradeIntent(
        symbol=snapshot.symbol,
        strategy_type="price_spread_convergence",
        bybit_side=bybit_side,
        hyperliquid_side=hyperliquid_side,
        target_notional_usd=target_notional_usd,
        gross_expected_bp=opportunity.gross_expected_bp,
        expected_net_bp=net_positive_result.expected_net_bp,
        created_at=snapshot.timestamp,
        metadata={
            "bybit_price": snapshot.bybit_price,
            "hyperliquid_price": snapshot.hyperliquid_price,
            "spread_bp": snapshot.spread_bp,
        },
    )
    return opportunity, trade_intent


def build_spread_signal(
    symbol: str,
    bybit_price: float,
    hyperliquid_price: float,
    entry_threshold_bp: float,
    expected_convergence_pct: float,
) -> SpreadSignal:
    snapshot = build_spread_snapshot(symbol, bybit_price, hyperliquid_price)
    spread_bp = snapshot.spread_bp
    gross_expected_bp = estimate_convergence_capture_bp(spread_bp, expected_convergence_pct)
    bybit_side, hyperliquid_side = _determine_pair_sides(snapshot)
    long_exchange = "bybit" if bybit_side == "Buy" else "hyperliquid"
    short_exchange = "hyperliquid" if long_exchange == "bybit" else "bybit"
    reason = "Bybit is cheaper than Hyperliquid" if long_exchange == "bybit" else "Hyperliquid is cheaper than Bybit"

    return SpreadSignal(
        symbol=symbol,
        bybit_price=bybit_price,
        hyperliquid_price=hyperliquid_price,
        spread_bp=spread_bp,
        gross_expected_bp=gross_expected_bp,
        long_exchange=long_exchange,
        short_exchange=short_exchange,
        meets_entry_threshold=abs(spread_bp) >= entry_threshold_bp,
        reason=reason,
    )
