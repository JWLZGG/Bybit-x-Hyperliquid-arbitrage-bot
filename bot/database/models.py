from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SystemEvent:
    timestamp: datetime
    level: str
    event_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


@dataclass(frozen=True)
class DashboardHealthData:
    bot_state: str
    bybit_status: str
    hyperliquid_status: str
    bybit_latency_ms: float | None
    hyperliquid_latency_ms: float | None
    paused: bool
    last_updated: str | None

@dataclass(frozen=True)
class PaperTrade:
    created_at: datetime
    symbol: str
    strategy_type: str
    status: str
    bybit_side: str
    hyperliquid_side: str
    entry_bybit_price: float
    entry_hyperliquid_price: float
    target_notional_usd: float
    expected_net_bp: float
    expected_gross_bp: float
    total_cost_bp: float
    entry_spread_bp: float | None = None
    exit_bybit_price: float | None = None
    exit_hyperliquid_price: float | None = None
    closed_at: datetime | None = None
    realized_pnl_usd: float | None = None
    realized_pnl_bp: float | None = None
    close_reason: str | None = None
    id: int | None = None
