from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountSnapshot:
    exchange: str
    equity_usd: float
    available_balance_usd: float
    margin_used_usd: float