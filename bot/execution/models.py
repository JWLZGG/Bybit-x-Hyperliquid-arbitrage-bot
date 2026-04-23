from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.signal_generator.models import TradeIntent


@dataclass(frozen=True)
class ExecutionIntent:
    symbol: str
    long_exchange: str
    short_exchange: str
    notional_usd: float
    strategy: str

    def to_trade_intent(self) -> TradeIntent:
        bybit_side = "Buy" if self.long_exchange == "bybit" else "Sell"
        hyperliquid_side = "Buy" if self.long_exchange == "hyperliquid" else "Sell"
        return TradeIntent(
            symbol=self.symbol,
            strategy_type=self.strategy,
            bybit_side=bybit_side,
            hyperliquid_side=hyperliquid_side,
            target_notional_usd=self.notional_usd,
            gross_expected_bp=0.0,
            expected_net_bp=0.0,
            created_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class LegExecutionResult:
    exchange: str
    side: str
    order_id: str
    requested_notional_usd: float
    filled_notional_usd: float
    average_fill_price: float
    status: str
    reason: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    symbol: str
    strategy_type: str
    status: str
    accepted: bool
    reason: str
    bybit_leg: LegExecutionResult
    hyperliquid_leg: LegExecutionResult
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def notional_usd(self) -> float:
        return min(self.bybit_leg.filled_notional_usd, self.hyperliquid_leg.filled_notional_usd)


@dataclass(frozen=True)
class PositionPair:
    symbol: str
    strategy_type: str
    bybit_side: str
    hyperliquid_side: str
    notional_usd: float
    entry_time: datetime
    status: str
    entry_bybit_price: float
    entry_hyperliquid_price: float
    current_pnl: float
    expected_net_bp: float
    delta_imbalance_bp: float = 0.0
    id: int | None = None

    @property
    def strategy(self) -> str:
        return self.strategy_type
