from bot.data_ingestion.account_models import AccountSnapshot
from bot.risk_engine.account_state import (
    apply_account_snapshot_overrides,
    combine_account_snapshots,
)


def test_combine_account_snapshots() -> None:
    bybit = AccountSnapshot(
        exchange="bybit",
        equity_usd=10000.0,
        available_balance_usd=8000.0,
        margin_used_usd=2000.0,
    )
    hyperliquid = AccountSnapshot(
        exchange="hyperliquid",
        equity_usd=10000.0,
        available_balance_usd=9000.0,
        margin_used_usd=1000.0,
    )

    combined = combine_account_snapshots(bybit, hyperliquid)

    assert combined.total_equity_usd == 20000.0
    assert combined.total_available_balance_usd == 17000.0
    assert combined.total_margin_used_usd == 3000.0
    assert combined.paired_available_balance_usd == 8000.0
    assert combined.margin_utilization == 3000.0 / 20000.0
    assert combined.margin_ratio_pct == (20000.0 / 3000.0) * 100


def test_apply_account_snapshot_overrides_uses_available_balance_as_equity_floor() -> None:
    raw_snapshot = AccountSnapshot(
        exchange="bybit",
        equity_usd=0.0,
        available_balance_usd=0.0,
        margin_used_usd=0.0,
    )

    effective_snapshot = apply_account_snapshot_overrides(
        raw_snapshot,
        available_balance_override_usd=5000.0,
    )

    assert effective_snapshot.available_balance_usd == 5000.0
    assert effective_snapshot.equity_usd == 5000.0
    assert effective_snapshot.margin_used_usd == 0.0
