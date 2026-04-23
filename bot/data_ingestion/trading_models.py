from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PositionExposure:
    exchange: str
    symbol: str
    side: str
    size: float
    entry_price: float
    notional_usd: float
    unrealized_pnl_usd: float = 0.0


@dataclass(frozen=True)
class OrderPlacement:
    exchange: str
    symbol: str
    order_id: str
    client_order_id: str | None
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderStatusSnapshot:
    exchange: str
    symbol: str
    order_id: str
    status: str
    side: str | None
    average_fill_price: float | None
    filled_size: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status.upper() in {"OPEN", "NEW", "PARTIALLY_FILLED", "PARTIALLYFILLED"}

    @property
    def is_filled(self) -> bool:
        return self.status.upper() == "FILLED"

    @property
    def is_rejected(self) -> bool:
        return self.status.upper() in {
            "REJECTED",
            "CANCELED",
            "CANCELLED",
            "MARGINCANCELED",
            "ERROR",
        }
