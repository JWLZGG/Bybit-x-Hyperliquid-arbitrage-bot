from __future__ import annotations

from dataclasses import dataclass

from bot.data_ingestion.account_models import AccountSnapshot


@dataclass(frozen=True)
class CombinedAccountState:
    bybit_equity_usd: float
    hyperliquid_equity_usd: float
    bybit_available_balance_usd: float
    hyperliquid_available_balance_usd: float
    bybit_margin_used_usd: float
    hyperliquid_margin_used_usd: float
    paired_available_balance_usd: float
    total_equity_usd: float
    total_available_balance_usd: float
    total_margin_used_usd: float
    margin_utilization: float
    margin_ratio_pct: float


def apply_account_snapshot_overrides(
    snapshot: AccountSnapshot,
    *,
    equity_override_usd: float | None = None,
    available_balance_override_usd: float | None = None,
    margin_used_override_usd: float | None = None,
) -> AccountSnapshot:
    effective_available_balance = (
        snapshot.available_balance_usd
        if available_balance_override_usd is None
        else available_balance_override_usd
    )
    effective_margin_used = (
        snapshot.margin_used_usd
        if margin_used_override_usd is None
        else margin_used_override_usd
    )
    effective_equity = snapshot.equity_usd if equity_override_usd is None else equity_override_usd

    # If only an available-balance override is provided, treat it as usable equity floor.
    if equity_override_usd is None:
        effective_equity = max(
            effective_equity,
            effective_available_balance + effective_margin_used,
        )

    return AccountSnapshot(
        exchange=snapshot.exchange,
        equity_usd=effective_equity,
        available_balance_usd=effective_available_balance,
        margin_used_usd=effective_margin_used,
    )


def combine_account_snapshots(
    bybit_snapshot: AccountSnapshot,
    hyperliquid_snapshot: AccountSnapshot,
) -> CombinedAccountState:
    total_equity = bybit_snapshot.equity_usd + hyperliquid_snapshot.equity_usd
    total_available = (
        bybit_snapshot.available_balance_usd
        + hyperliquid_snapshot.available_balance_usd
    )
    total_margin_used = (
        bybit_snapshot.margin_used_usd
        + hyperliquid_snapshot.margin_used_usd
    )

    margin_utilization = 0.0
    if total_equity > 0:
        margin_utilization = total_margin_used / total_equity

    margin_ratio_pct = float("inf")
    if total_margin_used > 0:
        margin_ratio_pct = (total_equity / total_margin_used) * 100

    return CombinedAccountState(
        bybit_equity_usd=bybit_snapshot.equity_usd,
        hyperliquid_equity_usd=hyperliquid_snapshot.equity_usd,
        bybit_available_balance_usd=bybit_snapshot.available_balance_usd,
        hyperliquid_available_balance_usd=hyperliquid_snapshot.available_balance_usd,
        bybit_margin_used_usd=bybit_snapshot.margin_used_usd,
        hyperliquid_margin_used_usd=hyperliquid_snapshot.margin_used_usd,
        paired_available_balance_usd=min(
            bybit_snapshot.available_balance_usd,
            hyperliquid_snapshot.available_balance_usd,
        ),
        total_equity_usd=total_equity,
        total_available_balance_usd=total_available,
        total_margin_used_usd=total_margin_used,
        margin_utilization=margin_utilization,
        margin_ratio_pct=margin_ratio_pct,
    )
