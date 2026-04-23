from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.config.config import Config
from bot.signal_generator.models import TradeIntent


@dataclass(frozen=True)
class RiskCheckResult:
    passed: bool
    reasons: tuple[str, ...] = ()
    suggested_notional: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.passed

    @property
    def reason(self) -> str:
        if not self.reasons:
            return "Risk checks passed"
        return "; ".join(self.reasons)


def check_margin_utilization(account_state, config: Config) -> RiskCheckResult:
    utilization = getattr(account_state, "margin_utilization", 0.0)
    if utilization > config.margin_utilization_cap:
        return RiskCheckResult(
            passed=False,
            reasons=(f"Margin utilization too high: {utilization:.2%}",),
            suggested_notional=0.0,
            details={"margin_utilization": utilization},
        )
    return RiskCheckResult(
        passed=True,
        suggested_notional=None,
        details={"margin_utilization": utilization},
    )


def check_max_position_notional(notional: float, config: Config) -> RiskCheckResult:
    suggested_notional = min(max(notional, 0.0), config.max_position_notional_usd)
    reasons: list[str] = []
    passed = True
    if notional <= 0:
        passed = False
        reasons.append("Proposed notional must be positive")
    if notional > config.max_position_notional_usd:
        passed = False
        reasons.append(
            (
                "Proposed notional exceeds max per-pair limit: "
                f"{notional:.2f} > {config.max_position_notional_usd:.2f}"
            )
        )
    return RiskCheckResult(
        passed=passed,
        reasons=tuple(reasons),
        suggested_notional=suggested_notional,
        details={"requested_notional_usd": notional},
    )



def check_orderbook_liquidity(
    symbol: str,
    notional: float,
    market_state,
    config: Config,
) -> RiskCheckResult:
    bybit_depth = market_state.average_depth_usd("bybit", symbol)
    hyperliquid_depth = market_state.average_depth_usd("hyperliquid", symbol)
    latest_bybit_depth = market_state.latest_depth_usd("bybit", symbol)
    latest_hyperliquid_depth = market_state.latest_depth_usd("hyperliquid", symbol)

    effective_bybit_depth = bybit_depth if bybit_depth is not None else latest_bybit_depth
    effective_hyperliquid_depth = (
        hyperliquid_depth if hyperliquid_depth is not None else latest_hyperliquid_depth
    )
    if effective_bybit_depth is None or effective_hyperliquid_depth is None:
        return RiskCheckResult(
            passed=False,
            reasons=("Orderbook depth unavailable",),
            suggested_notional=0.0,
        )

    depth_cap = min(effective_bybit_depth, effective_hyperliquid_depth) * config.liquidity_depth_fraction_limit
    if notional > depth_cap:
        return RiskCheckResult(
            passed=False,
            reasons=(
                f"Liquidity cap exceeded for {symbol}: {notional:.2f} > {depth_cap:.2f}",
            ),
            suggested_notional=round(max(depth_cap, 0.0), 2),
            details={
                "bybit_depth_usd": effective_bybit_depth,
                "hyperliquid_depth_usd": effective_hyperliquid_depth,
            },
        )

    return RiskCheckResult(
        passed=True,
        suggested_notional=round(notional, 2),
        details={
            "bybit_depth_usd": effective_bybit_depth,
            "hyperliquid_depth_usd": effective_hyperliquid_depth,
        },
    )


def check_latency(exchange_health: dict[str, dict[str, Any]], config: Config) -> RiskCheckResult:
    reasons: list[str] = []
    for exchange, health in exchange_health.items():
        latency_ms = float(health.get("latency_ms", 0.0) or 0.0)
        if latency_ms > config.latency_pause_threshold_ms:
            reasons.append(
                f"{exchange} latency too high: {latency_ms:.2f} ms > {config.latency_pause_threshold_ms:.2f} ms"
            )

    return RiskCheckResult(
        passed=not reasons,
        reasons=tuple(reasons),
    )


def check_volatility_pause(symbol: str, market_state, config: Config) -> RiskCheckResult:
    moves = [
        market_state.one_minute_move_pct("bybit", symbol),
        market_state.one_minute_move_pct("hyperliquid", symbol),
    ]
    max_move = max(move for move in moves if move is not None) if any(move is not None for move in moves) else None
    if max_move is not None and max_move > config.volatility_pause_threshold_pct:
        return RiskCheckResult(
            passed=False,
            reasons=(
                (
                    f"1-minute volatility too high for {symbol}: "
                    f"{max_move:.2f}% > {config.volatility_pause_threshold_pct:.2f}%"
                ),
            ),
            suggested_notional=0.0,
            details={"max_one_minute_move_pct": max_move},
        )
    return RiskCheckResult(
        passed=True,
        details={"max_one_minute_move_pct": max_move},
    )


def run_pre_trade_risk_checks(
    trade_intent: TradeIntent,
    account_state,
    market_state,
    config: Config,
    exchange_health: dict[str, dict[str, Any]],
) -> RiskCheckResult:
    checks = [
        check_margin_utilization(account_state, config),
        check_max_position_notional(trade_intent.target_notional_usd, config),
        check_orderbook_liquidity(
            trade_intent.symbol,
            trade_intent.target_notional_usd,
            market_state,
            config,
        ),
        check_latency(exchange_health, config),
        check_volatility_pause(trade_intent.symbol, market_state, config),
    ]

    reasons = [reason for result in checks for reason in result.reasons]
    suggested_values = [result.suggested_notional for result in checks if result.suggested_notional is not None]
    suggested_notional = round(min(suggested_values), 2) if suggested_values else round(trade_intent.target_notional_usd, 2)

    details: dict[str, Any] = {}
    for result in checks:
        details.update(result.details)

    return RiskCheckResult(
        passed=not reasons,
        reasons=tuple(reasons),
        suggested_notional=suggested_notional,
        details=details,
    )


def check_global_margin_utilization(
    current_margin_utilization: float,
    max_margin_utilization: float = 0.30,
) -> RiskCheckResult:
    class _AccountState:
        margin_utilization = current_margin_utilization

    class _Config:
        margin_utilization_cap = max_margin_utilization

    return check_margin_utilization(_AccountState(), _Config())  # type: ignore[arg-type]


def check_per_pair_notional(
    proposed_notional_usd: float,
    max_notional_usd: float = 10_000.0,
) -> RiskCheckResult:
    class _Config:
        max_position_notional_usd = max_notional_usd

    return check_max_position_notional(proposed_notional_usd, _Config())  # type: ignore[arg-type]


def check_latency_guard(
    observed_latency_ms: float,
    max_latency_ms: float,
) -> RiskCheckResult:
    return check_latency({"exchange": {"latency_ms": observed_latency_ms}}, Config(  # type: ignore[call-arg]
        environment="testnet",
        bybit_api_key="",
        bybit_api_secret="",
        hyperliquid_private_key="",
        bybit_account_type="UNIFIED",
        bybit_settle_coin="USDT",
        bybit_recv_window_ms=5000,
        hyperliquid_vault_address=None,
        hyperliquid_account_address=None,
        bybit_equity_override_usd=None,
        bybit_available_balance_override_usd=None,
        bybit_margin_used_override_usd=None,
        hyperliquid_equity_override_usd=None,
        hyperliquid_available_balance_override_usd=None,
        hyperliquid_margin_used_override_usd=None,
        bybit_rest_url="",
        hyperliquid_rest_url="",
        symbols=(),
        bybit_maker_fee_bp=0.0,
        hyperliquid_maker_fee_bp=0.0,
        slippage_buffer_bp=0.0,
        safety_margin_bp=0.0,
        min_net_expected_return_bp=0.0,
        funding_diff_threshold_bp=0.0,
        spread_threshold_bp=0.0,
        expected_convergence_pct=0.0,
        max_hold_minutes=0,
        max_position_notional_usd=0.0,
        margin_utilization_cap=0.0,
        latency_pause_threshold_ms=max_latency_ms,
        volatility_pause_threshold_pct=0.0,
        reconciliation_interval_seconds=0,
        poll_interval_seconds=0,
        dashboard_host="",
        dashboard_port=0,
        db_path="",
        log_path="",
        log_level="INFO",
        near_miss_threshold_ratio=0.0,
        liquidity_depth_fraction_limit=0.0,
        min_margin_ratio_pct=0.0,
        max_funding_prediction_horizon_hours=0,
        execution_order_timeout_seconds=0,
        execution_status_poll_interval_seconds=0.0,
        pause_on_zero_effective_capital=False,
        allow_degraded_mode=False,
        dashboard_enabled=False,
        dashboard_refresh_seconds=0,
        run_once=False,
    ))


def check_margin_ratio(
    margin_ratio_pct: float,
    min_margin_ratio_pct: float,
) -> RiskCheckResult:
    if margin_ratio_pct < min_margin_ratio_pct:
        return RiskCheckResult(
            passed=False,
            reasons=(f"Margin ratio too low: {margin_ratio_pct:.2f}%",),
            suggested_notional=0.0,
        )
    return RiskCheckResult(passed=True)


def check_one_minute_volatility(
    one_minute_move_pct: float | None,
    max_one_minute_move_pct: float,
) -> RiskCheckResult:
    if one_minute_move_pct is None:
        return RiskCheckResult(passed=True)
    if one_minute_move_pct > max_one_minute_move_pct:
        return RiskCheckResult(
            passed=False,
            reasons=(f"1-minute volatility too high: {one_minute_move_pct:.2f}%",),
            suggested_notional=0.0,
        )
    return RiskCheckResult(passed=True)


def check_liquidity_depth(
    proposed_notional_usd: float,
    average_depth_usd: float | None,
    max_depth_fraction: float,
) -> RiskCheckResult:
    if average_depth_usd is None:
        return RiskCheckResult(
            passed=False,
            reasons=("Orderbook depth unavailable",),
            suggested_notional=0.0,
        )
    depth_cap = average_depth_usd * max_depth_fraction
    if proposed_notional_usd > depth_cap:
        return RiskCheckResult(
            passed=False,
            reasons=(f"Proposed notional exceeds liquidity limit: {proposed_notional_usd:.2f} > {depth_cap:.2f}",),
            suggested_notional=round(depth_cap, 2),
        )
    return RiskCheckResult(
        passed=True,
        suggested_notional=round(proposed_notional_usd, 2),
    )
