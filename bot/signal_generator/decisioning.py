from __future__ import annotations

from bot.config.config import Settings
from bot.risk_engine.net_positive import evaluate_pre_trade_net_positive_check
from bot.signal_generator.decision_models import StrategyDecision


def classify_event_type(
    gross_expected_bp: float,
    threshold_bp: float,
    near_miss_threshold_ratio: float,
) -> str | None:
    if gross_expected_bp >= threshold_bp:
        return "opportunity"

    if gross_expected_bp >= threshold_bp * near_miss_threshold_ratio:
        return "near_miss"

    return None


def build_strategy_decision(
    strategy_type: str,
    symbol: str,
    gross_expected_bp: float,
    threshold_bp: float,
    reference_value_bp: float,
    long_exchange: str,
    short_exchange: str,
    settings: Settings,
    risk_blockers: list[str],
    metadata: dict[str, object] | None = None,
) -> StrategyDecision | None:
    event_type = classify_event_type(
        gross_expected_bp=gross_expected_bp,
        threshold_bp=threshold_bp,
        near_miss_threshold_ratio=settings.near_miss_threshold_ratio,
    )
    if event_type is None:
        return None

    net_positive = evaluate_pre_trade_net_positive_check(
        symbol=symbol,
        strategy_type=strategy_type,
        gross_expected_bp=gross_expected_bp,
        settings=settings,
    )

    will_trade = False
    if event_type == "near_miss":
        decision_state = "skipped_threshold"
        reason = f"Near miss below threshold {threshold_bp:.2f} bp"
    elif not net_positive.passed:
        decision_state = "skipped_net_positive"
        reason = net_positive.reason
    elif risk_blockers:
        decision_state = "skipped_risk"
        reason = "; ".join(risk_blockers)
    else:
        decision_state = "trade_candidate"
        reason = "Scanner found a tradable opportunity"
        will_trade = True

    return StrategyDecision(
        strategy_type=strategy_type,
        symbol=symbol,
        event_type=event_type,
        decision_state=decision_state,
        long_exchange=long_exchange,
        short_exchange=short_exchange,
        gross_expected_bp=gross_expected_bp,
        expected_net_bp=net_positive.expected_net_bp,
        threshold_bp=threshold_bp,
        reference_value_bp=reference_value_bp,
        total_cost_bp=net_positive.total_cost_bp,
        will_trade=will_trade,
        reason=reason,
        metadata=metadata or {},
    )
