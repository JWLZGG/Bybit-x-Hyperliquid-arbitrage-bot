from __future__ import annotations


def calculate_safe_notional(
    available_capital_usd: float,
    current_margin_utilization: float,
    max_margin_utilization: float,
    max_notional_usd: float,
) -> float:
    remaining_margin_headroom = max(
        max_margin_utilization - current_margin_utilization,
        0.0,
    )
    proposed = available_capital_usd * remaining_margin_headroom
    return round(min(proposed, max_notional_usd), 2)