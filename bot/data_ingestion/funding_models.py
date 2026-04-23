from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FundingRateSnapshot:
    exchange: str
    symbol: str
    raw_rate: float
    interval_hours: float
    rate_8h_equivalent: float
    observed_at: datetime
    predicted_rate_8h_equivalent: float | None = None

    @property
    def effective_rate_8h_equivalent(self) -> float:
        if self.predicted_rate_8h_equivalent is not None:
            return self.predicted_rate_8h_equivalent
        return self.rate_8h_equivalent
