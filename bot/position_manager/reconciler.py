from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from bot.database.models import SystemEvent
from bot.execution.models import PositionPair


def reconcile_expected_vs_actual_positions(
    position_pairs: list[PositionPair],
    live_positions: dict[str, dict[str, float]],
    tolerance_bp: float = 10.0,
) -> list[SystemEvent]:
    events: list[SystemEvent] = []
    for position_pair in position_pairs:
        delta_imbalance_bp = compute_delta_imbalance_bp(position_pair, live_positions)
        if delta_imbalance_bp > tolerance_bp:
            events.append(
                handle_reconciliation_mismatch(
                    position_pair=position_pair,
                    delta_imbalance_bp=delta_imbalance_bp,
                )
            )
    return events


def compute_delta_imbalance_bp(
    position_pair: PositionPair,
    live_positions: dict[str, dict[str, float]],
) -> float:
    symbol_positions = live_positions.get(position_pair.symbol, {})
    bybit_notional = abs(float(symbol_positions.get("bybit_notional_usd", position_pair.notional_usd)))
    hyperliquid_notional = abs(
        float(symbol_positions.get("hyperliquid_notional_usd", position_pair.notional_usd))
    )
    reference_notional = max(position_pair.notional_usd, 1.0)
    return abs(bybit_notional - hyperliquid_notional) / reference_notional * 10_000


def handle_reconciliation_mismatch(
    position_pair: PositionPair,
    delta_imbalance_bp: float,
) -> SystemEvent:
    return SystemEvent(
        timestamp=datetime.now(timezone.utc),
        level="WARNING",
        event_type="reconciliation_mismatch",
        message=(
            f"{position_pair.symbol} delta mismatch detected: "
            f"{delta_imbalance_bp:.2f} bp"
        ),
        metadata={
            "position_pair_id": position_pair.id,
            "symbol": position_pair.symbol,
            "delta_imbalance_bp": delta_imbalance_bp,
        },
    )


def mark_position_degraded(
    position_pair: PositionPair,
    reason: str,
) -> PositionPair:
    return replace(position_pair, status="DEGRADED", delta_imbalance_bp=position_pair.delta_imbalance_bp)
