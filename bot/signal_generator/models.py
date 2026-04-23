from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bot.risk_engine.net_positive import NetPositiveResult


@dataclass(frozen=True)
class FundingSnapshot:
    symbol: str
    bybit_rate_8h: float
    hyperliquid_rate_hourly: float
    hyperliquid_rate_8h_equivalent: float
    bybit_predicted_rate_8h: float | None
    hyperliquid_predicted_rate_8h: float | None
    timestamp: datetime

    @property
    def effective_bybit_rate_8h(self) -> float:
        return self.bybit_predicted_rate_8h or self.bybit_rate_8h

    @property
    def effective_hyperliquid_rate_8h(self) -> float:
        return self.hyperliquid_predicted_rate_8h or self.hyperliquid_rate_8h_equivalent


@dataclass(frozen=True)
class SpreadSnapshot:
    symbol: str
    bybit_price: float
    hyperliquid_price: float
    spread_bp: float
    timestamp: datetime


@dataclass(frozen=True)
class Opportunity:
    timestamp: datetime
    symbol: str
    strategy_type: str
    gross_expected_bp: float
    expected_net_bp: float
    total_cost_bp: float
    decision: str
    reject_reason: str | None
    bybit_value: float
    hyperliquid_value: float
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    strategy_type: str
    bybit_side: str
    hyperliquid_side: str
    target_notional_usd: float
    gross_expected_bp: float
    expected_net_bp: float
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "FundingSnapshot",
    "SpreadSnapshot",
    "Opportunity",
    "TradeIntent",
    "NetPositiveResult",
]
