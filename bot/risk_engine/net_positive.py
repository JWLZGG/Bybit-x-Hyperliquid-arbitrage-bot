from __future__ import annotations

import os
from dataclasses import dataclass

from bot.config.config import Config


@dataclass(frozen=True)
class NetPositiveResult:
    passed: bool
    gross_expected_bp: float
    expected_net_bp: float
    total_cost_bp: float
    reject_reason: str | None
    symbol: str
    strategy_type: str
    bybit_fee_bp: float
    hyperliquid_fee_bp: float
    round_trip_fees_bp: float

    @property
    def reason(self) -> str:
        if self.reject_reason:
            return self.reject_reason
        return "Expected net return is strictly positive"


def _get_fee_override(env_name: str) -> float | None:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return None
    return float(raw_value)


_LIVE_FEE_OVERRIDES: dict[str, float | None] = {
    "bybit": None,
    "hyperliquid": None,
}


def set_live_fee_override(exchange: str, fee_bp: float | None) -> None:
    normalized_exchange = exchange.strip().lower()
    if normalized_exchange not in _LIVE_FEE_OVERRIDES:
        raise ValueError(f"Unsupported exchange for fee override: {exchange}")
    _LIVE_FEE_OVERRIDES[normalized_exchange] = fee_bp


def clear_live_fee_overrides() -> None:
    for exchange in _LIVE_FEE_OVERRIDES:
        _LIVE_FEE_OVERRIDES[exchange] = None


def get_current_bybit_maker_fee(config: Config | None = None) -> float | None:
    return (
        _get_fee_override("CURRENT_BYBIT_MAKER_FEE_BP")
        or _LIVE_FEE_OVERRIDES["bybit"]
        or (config.bybit_maker_fee_bp if config else None)
    )


def get_current_hyperliquid_maker_fee(config: Config | None = None) -> float | None:
    return (
        _get_fee_override("CURRENT_HYPERLIQUID_MAKER_FEE_BP")
        or _LIVE_FEE_OVERRIDES["hyperliquid"]
        or (config.hyperliquid_maker_fee_bp if config else None)
    )


def calculate_total_cost_bp(
    config: Config,
    bybit_fee_bp: float | None = None,
    hyperliquid_fee_bp: float | None = None,
) -> tuple[float, float, float, float]:
    effective_bybit_fee = bybit_fee_bp if bybit_fee_bp is not None else config.bybit_maker_fee_bp
    effective_hyperliquid_fee = (
        hyperliquid_fee_bp if hyperliquid_fee_bp is not None else config.hyperliquid_maker_fee_bp
    )
    round_trip_fees_bp = 2 * (effective_bybit_fee + effective_hyperliquid_fee)
    total_cost_bp = round_trip_fees_bp + config.slippage_buffer_bp + config.safety_margin_bp
    return total_cost_bp, round_trip_fees_bp, effective_bybit_fee, effective_hyperliquid_fee


def calculate_expected_net_bp(
    gross_expected_bp: float,
    total_cost_bp: float,
) -> float:
    return gross_expected_bp - total_cost_bp


def pre_trade_net_positive_check(
    symbol: str,
    strategy_type: str,
    gross_expected_bp: float,
    config: Config,
) -> NetPositiveResult:
    bybit_fee_bp = get_current_bybit_maker_fee(config) or config.bybit_maker_fee_bp
    hyperliquid_fee_bp = (
        get_current_hyperliquid_maker_fee(config) or config.hyperliquid_maker_fee_bp
    )
    total_cost_bp, round_trip_fees_bp, _, _ = calculate_total_cost_bp(
        config=config,
        bybit_fee_bp=bybit_fee_bp,
        hyperliquid_fee_bp=hyperliquid_fee_bp,
    )
    expected_net_bp = calculate_expected_net_bp(gross_expected_bp, total_cost_bp)
    passed = expected_net_bp > config.min_net_expected_return_bp
    reject_reason = None
    if not passed:
        reject_reason = (
            "No net-positive opportunity: "
            f"gross={gross_expected_bp:.2f} bp, cost={total_cost_bp:.2f} bp, "
            f"net={expected_net_bp:.2f} bp"
        )

    return NetPositiveResult(
        passed=passed,
        gross_expected_bp=gross_expected_bp,
        expected_net_bp=expected_net_bp,
        total_cost_bp=total_cost_bp,
        reject_reason=reject_reason,
        symbol=symbol,
        strategy_type=strategy_type,
        bybit_fee_bp=bybit_fee_bp,
        hyperliquid_fee_bp=hyperliquid_fee_bp,
        round_trip_fees_bp=round_trip_fees_bp,
    )


def evaluate_pre_trade_net_positive_check(
    symbol: str,
    strategy_type: str,
    gross_expected_bp: float,
    settings: Config,
) -> NetPositiveResult:
    return pre_trade_net_positive_check(
        symbol=symbol,
        strategy_type=strategy_type,
        gross_expected_bp=gross_expected_bp,
        config=settings,
    )
