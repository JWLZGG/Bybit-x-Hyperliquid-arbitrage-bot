from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BestBidAsk:
    exchange: str
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    timestamp: datetime

    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread_bp(self) -> float:
        if self.mid_price <= 0:
            return 0.0
        return ((self.ask_price - self.bid_price) / self.mid_price) * 10_000
