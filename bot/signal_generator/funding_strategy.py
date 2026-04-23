from __future__ import annotations

from datetime import datetime, timezone

from bot.config.config import Config
from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.risk_engine.net_positive import NetPositiveResult, pre_trade_net_positive_check
from bot.signal_generator.funding_signal import FundingSignal
from bot.signal_generator.models import FundingSnapshot, Opportunity, TradeIntent


def normalise_hyperliquid_to_8h(hourly_rate: float) -> float:
    return hourly_rate * 8.0


def build_funding_snapshot(
    bybit_snapshot: FundingRateSnapshot,
    hyperliquid_snapshot: FundingRateSnapshot,
) -> FundingSnapshot:
    if bybit_snapshot.symbol != hyperliquid_snapshot.symbol:
        raise ValueError("Funding snapshots must refer to the same symbol")

    return FundingSnapshot(
        symbol=bybit_snapshot.symbol,
        bybit_rate_8h=bybit_snapshot.rate_8h_equivalent,
        hyperliquid_rate_hourly=hyperliquid_snapshot.raw_rate,
        hyperliquid_rate_8h_equivalent=normalise_hyperliquid_to_8h(hyperliquid_snapshot.raw_rate),
        bybit_predicted_rate_8h=bybit_snapshot.predicted_rate_8h_equivalent,
        hyperliquid_predicted_rate_8h=hyperliquid_snapshot.predicted_rate_8h_equivalent,
        timestamp=max(bybit_snapshot.observed_at, hyperliquid_snapshot.observed_at),
    )


def calculate_funding_diff_bp(snapshot: FundingSnapshot) -> float:
    return (snapshot.effective_hyperliquid_rate_8h - snapshot.effective_bybit_rate_8h) * 10_000


def determine_pair_sides(snapshot: FundingSnapshot) -> tuple[str, str]:
    if snapshot.effective_bybit_rate_8h <= snapshot.effective_hyperliquid_rate_8h:
        return "Buy", "Sell"
    return "Sell", "Buy"


def _build_funding_opportunity(
    snapshot: FundingSnapshot,
    config: Config,
    net_positive_result: NetPositiveResult,
) -> Opportunity:
    gross_expected_bp = abs(calculate_funding_diff_bp(snapshot))
    threshold_bp = config.funding_diff_threshold_bp

    if gross_expected_bp >= threshold_bp and net_positive_result.passed:
        decision = "accepted"
        reject_reason = None
    elif gross_expected_bp >= threshold_bp:
        decision = "rejected_net_positive"
        reject_reason = net_positive_result.reject_reason
    elif gross_expected_bp >= threshold_bp * config.near_miss_threshold_ratio:
        decision = "near_miss"
        reject_reason = "Funding differential below entry threshold"
    else:
        decision = "near_miss"
        reject_reason = "Funding differential below near-miss threshold"

    return Opportunity(
        timestamp=snapshot.timestamp,
        symbol=snapshot.symbol,
        strategy_type="funding_arbitrage",
        gross_expected_bp=gross_expected_bp,
        expected_net_bp=net_positive_result.expected_net_bp,
        total_cost_bp=net_positive_result.total_cost_bp,
        decision=decision,
        reject_reason=reject_reason,
        bybit_value=snapshot.effective_bybit_rate_8h,
        hyperliquid_value=snapshot.effective_hyperliquid_rate_8h,
        metadata={
            "funding_diff_bp": calculate_funding_diff_bp(snapshot),
            "bybit_rate_8h": snapshot.bybit_rate_8h,
            "hyperliquid_rate_hourly": snapshot.hyperliquid_rate_hourly,
            "hyperliquid_rate_8h_equivalent": snapshot.hyperliquid_rate_8h_equivalent,
        },
    )


def evaluate_funding_opportunity(
    snapshot: FundingSnapshot,
    config: Config,
) -> tuple[Opportunity, NetPositiveResult]:
    gross_expected_bp = abs(calculate_funding_diff_bp(snapshot))
    net_positive_result = pre_trade_net_positive_check(
        symbol=snapshot.symbol,
        strategy_type="funding_arbitrage",
        gross_expected_bp=gross_expected_bp,
        config=config,
    )
    opportunity = _build_funding_opportunity(snapshot, config, net_positive_result)
    return opportunity, net_positive_result


def maybe_emit_trade_intent(
    snapshot: FundingSnapshot,
    config: Config,
    target_notional_usd: float,
) -> tuple[Opportunity, TradeIntent | None]:
    opportunity, net_positive_result = evaluate_funding_opportunity(snapshot, config)
    if opportunity.decision != "accepted":
        return opportunity, None

    bybit_side, hyperliquid_side = determine_pair_sides(snapshot)
    trade_intent = TradeIntent(
        symbol=snapshot.symbol,
        strategy_type="funding_arbitrage",
        bybit_side=bybit_side,
        hyperliquid_side=hyperliquid_side,
        target_notional_usd=target_notional_usd,
        gross_expected_bp=opportunity.gross_expected_bp,
        expected_net_bp=net_positive_result.expected_net_bp,
        created_at=snapshot.timestamp,
        metadata={
            "bybit_price": 0.0,
            "hyperliquid_price": 0.0,
            "bybit_rate_8h": snapshot.effective_bybit_rate_8h,
            "hyperliquid_rate_8h": snapshot.effective_hyperliquid_rate_8h,
        },
    )
    return opportunity, trade_intent


def build_funding_signal(
    bybit_snapshot: FundingRateSnapshot,
    hyperliquid_snapshot: FundingRateSnapshot,
    entry_threshold_bp: float,
) -> FundingSignal:
    snapshot = build_funding_snapshot(bybit_snapshot, hyperliquid_snapshot)
    diff_bp = calculate_funding_diff_bp(snapshot)
    bybit_side, hyperliquid_side = determine_pair_sides(snapshot)
    long_exchange = "bybit" if bybit_side == "Buy" else "hyperliquid"
    short_exchange = "hyperliquid" if long_exchange == "bybit" else "bybit"
    reason = "Bybit funding is lower than Hyperliquid" if long_exchange == "bybit" else "Hyperliquid funding is lower than Bybit"

    return FundingSignal(
        symbol=snapshot.symbol,
        bybit_rate_8h=snapshot.effective_bybit_rate_8h,
        hyperliquid_rate_8h=snapshot.effective_hyperliquid_rate_8h,
        normalized_diff_bp=diff_bp,
        gross_expected_bp=abs(diff_bp),
        long_exchange=long_exchange,
        short_exchange=short_exchange,
        meets_entry_threshold=abs(diff_bp) >= entry_threshold_bp,
        reason=reason,
    )
