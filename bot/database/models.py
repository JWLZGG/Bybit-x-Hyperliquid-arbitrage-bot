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
