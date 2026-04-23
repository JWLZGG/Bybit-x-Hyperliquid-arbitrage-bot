from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyDecision:
    strategy_type: str
    symbol: str
    event_type: str
    decision_state: str
    long_exchange: str
    short_exchange: str
    gross_expected_bp: float
    expected_net_bp: float
    threshold_bp: float
    reference_value_bp: float
    total_cost_bp: float
    will_trade: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
