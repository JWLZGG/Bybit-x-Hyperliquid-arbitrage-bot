from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter

from bot.config.config import Config, load_config, reload_config_if_needed
from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient
from bot.database.models import SystemEvent
from bot.database.repository import (
    get_open_positions,
    insert_execution_result,
    insert_funding_snapshot,
    insert_heartbeat,
    insert_market_snapshot,
    insert_opportunity,
    insert_position_pair,
    insert_system_event,
    update_position_pair_status,
)
from bot.database.schema import initialize_database
from bot.execution.router import submit_execution_intent
from bot.execution.paper_trade_manager import reconcile_open_paper_trades
from bot.monitoring.alerts import (
    send_bot_started_alert,
    send_disconnect_alert,
    send_one_leg_risk_alert,
    send_pause_trigger_alert,
    send_trade_entered_alert,
    send_trade_rejected_alert,
)
from bot.monitoring.dashboard import run_dashboard_server
from bot.monitoring.logger import (
    configure_logger,
    log_execution_result,
    log_opportunity,
    log_reconciliation_event,
    log_rejection,
    log_system_health,
    log_trade_intent,
)
from bot.position_manager.reconciler import (
    compute_delta_imbalance_bp,
    handle_reconciliation_mismatch,
    mark_position_degraded,
    reconcile_expected_vs_actual_positions,
)
from bot.position_manager.service import build_position_pair_from_execution
from bot.risk_engine.account_state import (
    apply_account_snapshot_overrides,
    combine_account_snapshots,
)
from bot.risk_engine.checks import run_pre_trade_risk_checks
from bot.risk_engine.market_state import MarketStateTracker
from bot.risk_engine.net_positive import clear_live_fee_overrides, set_live_fee_override
from bot.risk_engine.sizing import calculate_safe_notional
from bot.signal_generator.funding_strategy import (
    build_funding_snapshot,
    maybe_emit_trade_intent as maybe_emit_funding_trade_intent,
)
from bot.signal_generator.market_data_sanity import check_cross_exchange_price_sanity
from bot.signal_generator.models import Opportunity, TradeIntent
from bot.signal_generator.spread_strategy import (
    build_spread_snapshot,
    maybe_emit_trade_intent as maybe_emit_spread_trade_intent,
)

from bot.analytics.pnl import compute_paper_trade_summary
from bot.database.paper_trade_repository import list_paper_trades

class StartupPreflightError(RuntimeError):
    """Raised when the bot cannot determine usable paired capital at startup."""


async def timed_call(coroutine):
    started_at = perf_counter()
    result = await coroutine
    latency_ms = (perf_counter() - started_at) * 1000
    return result, latency_ms


def _build_exchange_health(bybit_latency_ms: float, hyperliquid_latency_ms: float) -> dict[str, dict[str, float]]:
    return {
        "bybit": {"latency_ms": bybit_latency_ms},
        "hyperliquid": {"latency_ms": hyperliquid_latency_ms},
    }


async def _build_live_positions(
    config: Config,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
) -> dict[str, dict[str, float]]:
    symbols = config.symbols
    bybit_notionals, hyperliquid_notionals = await asyncio.gather(
        bybit_client.get_position_notionals(symbols),
        hyperliquid_client.get_position_notionals(symbols),
    )

    live_positions: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        live_positions[symbol] = {
            "bybit_notional_usd": float(bybit_notionals.get(symbol, 0.0)),
            "hyperliquid_notional_usd": float(hyperliquid_notionals.get(symbol, 0.0)),
        }
    return live_positions


def _apply_account_snapshot_config_overrides(
    config: Config,
    bybit_account,
    hyperliquid_account,
):
    effective_bybit_account = apply_account_snapshot_overrides(
        bybit_account,
        equity_override_usd=config.bybit_equity_override_usd,
        available_balance_override_usd=config.bybit_available_balance_override_usd,
        margin_used_override_usd=config.bybit_margin_used_override_usd,
    )
    effective_hyperliquid_account = apply_account_snapshot_overrides(
        hyperliquid_account,
        equity_override_usd=config.hyperliquid_equity_override_usd,
        available_balance_override_usd=config.hyperliquid_available_balance_override_usd,
        margin_used_override_usd=config.hyperliquid_margin_used_override_usd,
    )
    return effective_bybit_account, effective_hyperliquid_account


def _build_startup_capital_preflight_issues(
    config: Config,
    *,
    raw_bybit_account,
    raw_hyperliquid_account,
    effective_bybit_account,
    effective_hyperliquid_account,
    hyperliquid_resolved_user: str,
    hyperliquid_resolved_role: str,
) -> list[str]:
    issues: list[str] = []

    bybit_effective_zero = effective_bybit_account.available_balance_usd <= 0
    hyper_effective_zero = effective_hyperliquid_account.available_balance_usd <= 0

    if bybit_effective_zero:
        if (
            config.bybit_available_balance_override_usd is None
            and config.bybit_equity_override_usd is None
        ):
            issues.append(
                "Bybit usable capital is zero and no override is configured. "
                "Fund the Bybit UNIFIED account behind this API key or set "
                "BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD (and optionally BYBIT_EQUITY_OVERRIDE_USD)."
            )
        elif config.bybit_available_balance_override_usd is None:
            issues.append(
                "Bybit equity override is set without BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD. "
                "Set BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD so pair sizing has usable capital."
            )

    if hyper_effective_zero:
        if config.hyperliquid_account_address is None and config.hyperliquid_vault_address is None:
            issues.append(
                "Hyperliquid account target is not configured. Set HYPERLIQUID_ACCOUNT_ADDRESS "
                "to the funded user/subaccount address, or HYPERLIQUID_VAULT_ADDRESS if using a vault."
            )
        if hyperliquid_resolved_role == "missing":
            issues.append(
                "Hyperliquid private key resolves to a wallet with role 'missing'. "
                f"Resolved wallet: {hyperliquid_resolved_user}. Check HYPERLIQUID_PRIVATE_KEY or "
                "set HYPERLIQUID_ACCOUNT_ADDRESS to the funded trading account."
            )
        if (
            config.hyperliquid_available_balance_override_usd is None
            and config.hyperliquid_equity_override_usd is None
        ):
            issues.append(
                "Hyperliquid usable capital is zero and no override is configured. "
                "Fund the resolved Hyperliquid account or set "
                "HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD (and optionally HYPERLIQUID_EQUITY_OVERRIDE_USD)."
            )
        elif config.hyperliquid_available_balance_override_usd is None:
            issues.append(
                "Hyperliquid equity override is set without HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD. "
                "Set HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD so pair sizing has usable capital."
            )

    if (
        raw_bybit_account.available_balance_usd <= 0
        and raw_hyperliquid_account.available_balance_usd <= 0
        and not issues
    ):
        issues.append(
            "Both raw exchange balances are zero. Verify the funded exchange accounts and API credentials."
        )

    return issues


async def _perform_startup_capital_preflight(
    config: Config,
    logger,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
) -> None:
    raw_bybit_account, raw_hyperliquid_account = await asyncio.gather(
        bybit_client.get_account_snapshot(),
        hyperliquid_client.get_account_snapshot(),
    )
    effective_bybit_account, effective_hyperliquid_account = _apply_account_snapshot_config_overrides(
        config,
        raw_bybit_account,
        raw_hyperliquid_account,
    )
    account_state = combine_account_snapshots(
        effective_bybit_account,
        effective_hyperliquid_account,
    )
    hyperliquid_resolved_user, hyperliquid_resolved_role = await hyperliquid_client.resolve_user_identity()

    has_bybit_override = (
        config.bybit_equity_override_usd is not None
        or config.bybit_available_balance_override_usd is not None
    )
    has_hyperliquid_override = (
        config.hyperliquid_equity_override_usd is not None
        or config.hyperliquid_available_balance_override_usd is not None
    )
    simulated_capital_mode = (
        raw_bybit_account.available_balance_usd <= 0
        and raw_hyperliquid_account.available_balance_usd <= 0
        and has_bybit_override
        and has_hyperliquid_override
    )

    logger.info(
        "Startup capital preflight | mode=%s | raw_bybit_available=%s | raw_hyper_available=%s "
        "| effective_bybit_available=%s | effective_hyper_available=%s | paired_available=%s "
        "| hyperliquid_user=%s | hyperliquid_role=%s",
        "simulated" if simulated_capital_mode else "funded",
        raw_bybit_account.available_balance_usd,
        raw_hyperliquid_account.available_balance_usd,
        effective_bybit_account.available_balance_usd,
        effective_hyperliquid_account.available_balance_usd,
        account_state.paired_available_balance_usd,
        hyperliquid_resolved_user,
        hyperliquid_resolved_role,
    )

    issues = _build_startup_capital_preflight_issues(
        config,
        raw_bybit_account=raw_bybit_account,
        raw_hyperliquid_account=raw_hyperliquid_account,
        effective_bybit_account=effective_bybit_account,
        effective_hyperliquid_account=effective_hyperliquid_account,
        hyperliquid_resolved_user=hyperliquid_resolved_user,
        hyperliquid_resolved_role=hyperliquid_resolved_role,
    )
    if not issues:
        logger.info(
            "Startup capital preflight passed | mode=%s",
            "simulated" if simulated_capital_mode else "funded",
        )
        return

    for index, issue in enumerate(issues, start=1):
        if simulated_capital_mode and "Both raw exchange balances are zero" in issue:
            logger.warning(
                "Startup capital preflight note %s | %s | simulated-capital overrides are active",
                index,
                issue,
            )
        else:
            logger.error("Startup capital preflight issue %s | %s", index, issue)

    if config.pause_on_zero_effective_capital and account_state.paired_available_balance_usd <= 0:
        raise StartupPreflightError(
            "Startup capital preflight failed. "
            + " ".join(f"[{index}] {issue}" for index, issue in enumerate(issues, start=1))
        )

def _system_event(
    level: str,
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> SystemEvent:
    return SystemEvent(
        timestamp=datetime.now(timezone.utc),
        level=level,
        event_type=event_type,
        message=message,
        metadata=metadata or {},
    )


def _enrich_trade_intent_with_prices(
    trade_intent: TradeIntent,
    bybit_price: float,
    hyperliquid_price: float,
) -> TradeIntent:
    metadata = dict(trade_intent.metadata)
    metadata["bybit_price"] = bybit_price
    metadata["hyperliquid_price"] = hyperliquid_price
    return replace(trade_intent, metadata=metadata)


def _finalize_non_selected_accepted_opportunity(
    opportunity: Opportunity,
    selected_strategy_type: str,
) -> Opportunity:
    return replace(
        opportunity,
        decision="accepted",
        reject_reason=f"Deferred because {selected_strategy_type} has priority",
    )

def _can_downsize_to_suggested_notional(risk_result) -> bool:
    if risk_result.passed:
        return False

    suggested = getattr(risk_result, "suggested_notional", None)
    if suggested is None or suggested <= 0:
        return False

    reasons = tuple(getattr(risk_result, "reasons", ()))
    if not reasons:
        return False

    # Only auto-downsize when the blocker is sizing/liquidity, not latency/volatility/etc.
    allowed_prefixes = (
        "Liquidity cap exceeded",
        "Proposed notional exceeds",
        "Proposed notional must be positive",
    )

    return all(any(reason.startswith(prefix) for prefix in allowed_prefixes) for reason in reasons)

async def process_symbol_full(
    config: Config,
    logger,
    symbol: str,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    account_state,
    market_state: MarketStateTracker,
) -> None:
    (
        (bybit_ticker, bybit_ticker_latency_ms),
        (hyperliquid_ticker, hyperliquid_ticker_latency_ms),
        (bybit_funding, bybit_funding_latency_ms),
        (hyperliquid_funding, hyperliquid_funding_latency_ms),
        (bybit_depth_usd, bybit_depth_latency_ms),
        (hyperliquid_depth_usd, hyperliquid_depth_latency_ms),
    ) = await asyncio.gather(
        timed_call(bybit_client.get_ticker(symbol)),
        timed_call(hyperliquid_client.get_ticker(symbol)),
        timed_call(bybit_client.get_latest_funding_rate(symbol)),
        timed_call(hyperliquid_client.get_latest_funding_rate(symbol)),
        timed_call(bybit_client.get_orderbook_depth_usd(symbol)),
        timed_call(hyperliquid_client.get_orderbook_depth_usd(symbol)),
    )

    logger.info(
       "Price snapshot %s | bybit_mark=%s | hyperliquid_mark=%s | bybit_last=%s | hyperliquid_last=%s",
       symbol,
       bybit_ticker.mark_price,
       hyperliquid_ticker.mark_price,
       bybit_ticker.last_price,
       hyperliquid_ticker.last_price,
    )

    bybit_mark = float(bybit_ticker.mark_price)
    bybit_index = float(bybit_ticker.index_price or 0.0)
    hl_mark = float(hyperliquid_ticker.mark_price)

    if bybit_index > 0:
        bybit_mark_index_divergence_bp = abs(bybit_mark - bybit_index) / bybit_index * 10000
    else:
        bybit_mark_index_divergence_bp = 0.0

    if bybit_index > 0 and bybit_mark_index_divergence_bp > 500:
        logger.warning(
           "Reconciliation event market_data_sanity | level=WARNING | message=%s Bybit mark/index divergence too large",
           symbol,
        )
        return

    bybit_latency_ms = max(bybit_ticker_latency_ms, bybit_funding_latency_ms, bybit_depth_latency_ms)
    hyperliquid_latency_ms = max(
        hyperliquid_ticker_latency_ms,
        hyperliquid_funding_latency_ms,
        hyperliquid_depth_latency_ms,
    )

    market_state.record_price("bybit", symbol, bybit_ticker.mark_price, bybit_ticker.timestamp)
    market_state.record_price(
        "hyperliquid",
        symbol,
        hyperliquid_ticker.mark_price,
        hyperliquid_ticker.timestamp,
    )
    market_state.record_depth("bybit", symbol, bybit_depth_usd, bybit_ticker.timestamp)
    market_state.record_depth(
        "hyperliquid",
        symbol,
        hyperliquid_depth_usd,
        hyperliquid_ticker.timestamp,
    )

    insert_market_snapshot(
        config.db_path,
        "bybit",
        symbol,
        bybit_ticker.last_price,
        bybit_ticker.mark_price,
        bybit_ticker.index_price,
        bybit_latency_ms,
        bybit_depth_usd,
        bybit_ticker.timestamp.isoformat(),
    )
    insert_market_snapshot(
        config.db_path,
        "hyperliquid",
        symbol,
        hyperliquid_ticker.last_price,
        hyperliquid_ticker.mark_price,
        None,
        hyperliquid_latency_ms,
        hyperliquid_depth_usd,
        hyperliquid_ticker.timestamp.isoformat(),
    )
    insert_funding_snapshot(
        config.db_path,
        bybit_funding.exchange,
        symbol,
        bybit_funding.raw_rate,
        bybit_funding.interval_hours,
        bybit_funding.rate_8h_equivalent,
        bybit_funding.predicted_rate_8h_equivalent,
        bybit_funding_latency_ms,
        bybit_funding.observed_at.isoformat(),
    )
    insert_funding_snapshot(
        config.db_path,
        hyperliquid_funding.exchange,
        symbol,
        hyperliquid_funding.raw_rate,
        hyperliquid_funding.interval_hours,
        hyperliquid_funding.rate_8h_equivalent,
        hyperliquid_funding.predicted_rate_8h_equivalent,
        hyperliquid_funding_latency_ms,
        hyperliquid_funding.observed_at.isoformat(),
    )

    sanity_result = check_cross_exchange_price_sanity(
        bybit_ticker.index_price,
        hyperliquid_ticker.mark_price,
        0.15,
    )
    if not sanity_result.sane:
        event = _system_event(
            "WARNING",
            "market_data_sanity",
            f"{symbol} market data sanity failed",
            {
                "relative_diff": sanity_result.relative_diff,
                "reason": sanity_result.reason,
                "bybit_index_price": bybit_ticker.index_price,
                "bybit_mark_price": bybit_ticker.mark_price,
                "hyperliquid_mark_price": hyperliquid_ticker.mark_price,
            },
        )
        insert_system_event(config.db_path, event)
        log_reconciliation_event(logger, event)
        return

    if bybit_ticker.index_price > 0:
        bybit_mark_index_gap = abs(bybit_ticker.mark_price - bybit_ticker.index_price) / bybit_ticker.index_price
        if bybit_mark_index_gap > 0.10:
            event = _system_event(
                "WARNING",
                "market_data_sanity",
                f"{symbol} Bybit mark/index divergence too large",
                {
                    "bybit_mark_price": bybit_ticker.mark_price,
                    "bybit_index_price": bybit_ticker.index_price,
                    "relative_diff": bybit_mark_index_gap,
                    "reason": "Bybit mark/index divergence exceeded 10%",
                },
            )
            insert_system_event(config.db_path, event)
            log_reconciliation_event(logger, event)
            return

    cross_exchange_mark_gap = abs(bybit_ticker.mark_price - hyperliquid_ticker.mark_price) / max(hyperliquid_ticker.mark_price, 1e-9)
    if cross_exchange_mark_gap > 0.20:
        event = _system_event(
            "WARNING",
            "market_data_sanity",
            f"{symbol} cross-exchange mark divergence too large",
            {
                "bybit_mark_price": bybit_ticker.mark_price,
                "hyperliquid_mark_price": hyperliquid_ticker.mark_price,
                "relative_diff": cross_exchange_mark_gap,
                "reason": "Cross-exchange mark divergence exceeded 20%",
            },
        )
        insert_system_event(config.db_path, event)
        log_reconciliation_event(logger, event)
        return

    proposed_notional = calculate_safe_notional(
        available_capital_usd=account_state.paired_available_balance_usd,
        current_margin_utilization=account_state.margin_utilization,
        max_margin_utilization=config.margin_utilization_cap,
        max_notional_usd=config.max_position_notional_usd,
    )

    logger.info(
        "Sizing debug %s | paired_available_capital=%s | bybit_available=%s | hyper_available=%s | margin_utilization=%s | margin_cap=%s | max_notional=%s | proposed_notional=%s",
        symbol,
        account_state.paired_available_balance_usd,
        account_state.bybit_available_balance_usd,
        account_state.hyperliquid_available_balance_usd,
        account_state.margin_utilization,
        config.margin_utilization_cap,
        config.max_position_notional_usd,
        proposed_notional,
    )

    funding_snapshot = build_funding_snapshot(bybit_funding, hyperliquid_funding)
    funding_opportunity, funding_intent = maybe_emit_funding_trade_intent(
        funding_snapshot,
        config,
        proposed_notional,
    )
    if funding_intent is not None:
        funding_intent = _enrich_trade_intent_with_prices(
            funding_intent,
            bybit_ticker.mark_price,
            hyperliquid_ticker.mark_price,
        )

    spread_snapshot = build_spread_snapshot(
        symbol,
        bybit_ticker.mark_price,
        hyperliquid_ticker.mark_price,
        timestamp=max(bybit_ticker.timestamp, hyperliquid_ticker.timestamp),
    )
    spread_opportunity, spread_intent = maybe_emit_spread_trade_intent(
        spread_snapshot,
        config,
        proposed_notional,
    )
    if spread_intent is not None:
        spread_intent = _enrich_trade_intent_with_prices(
            spread_intent,
            bybit_ticker.mark_price,
            hyperliquid_ticker.mark_price,
        )

    opportunities: list[tuple[Opportunity, TradeIntent | None]] = [
        (funding_opportunity, funding_intent),
        (spread_opportunity, spread_intent),
    ]

    accepted_candidates = [
        (opportunity, intent)
        for opportunity, intent in opportunities
        if intent is not None
    ]

    selected: tuple[Opportunity, TradeIntent] | None = None
    if accepted_candidates:
        priority = {"funding_arbitrage": 0, "price_spread_convergence": 1}
        selected = sorted(
            accepted_candidates,
            key=lambda item: priority.get(item[0].strategy_type, 99),
        )[0]

    for opportunity, intent in opportunities:
        if intent is None:
            insert_opportunity(config.db_path, opportunity)
            log_opportunity(logger, opportunity)
            if opportunity.decision != "near_miss":
                log_rejection(logger, opportunity, opportunity.reject_reason or opportunity.decision)
                send_trade_rejected_alert(logger, opportunity)
            continue

        if selected is not None and opportunity.strategy_type != selected[0].strategy_type:
            deferred = _finalize_non_selected_accepted_opportunity(
                opportunity,
                selected_strategy_type=selected[0].strategy_type,
            )
            insert_opportunity(config.db_path, deferred)
            log_opportunity(logger, deferred)

    if selected is None:
        return

    selected_opportunity, selected_intent = selected
    exchange_health = _build_exchange_health(bybit_latency_ms, hyperliquid_latency_ms)

    risk_result = run_pre_trade_risk_checks(
        selected_intent,
        account_state,
        market_state,
        config,
        exchange_health,
    )
    logger.info(
        "Risk result %s | passed=%s | reasons=%s | suggested_notional=%s | details=%s",
        selected_intent.symbol,
        risk_result.passed,
        risk_result.reasons,
        risk_result.suggested_notional,
        risk_result.details,
    )

    executable_intent = selected_intent

    if not risk_result.passed:
        if _can_downsize_to_suggested_notional(risk_result):
            resized_notional = round(float(risk_result.suggested_notional), 2)
            logger.info(
                "Downsizing %s %s notional from %s to %s based on risk suggestion",
                selected_intent.symbol,
                selected_intent.strategy_type,
                selected_intent.target_notional_usd,
                resized_notional,
            )
            executable_intent = replace(
                selected_intent,
                target_notional_usd=resized_notional,
            )
        else:
            rejected = replace(
                selected_opportunity,
                decision="rejected_risk",
                reject_reason="; ".join(risk_result.reasons),
            )
            insert_opportunity(config.db_path, rejected)
            log_opportunity(logger, rejected)
            log_rejection(logger, rejected, rejected.reject_reason or "Risk rejected")
            send_trade_rejected_alert(logger, rejected)

            if any(
                "latency" in reason.lower() or "volatility" in reason.lower()
                for reason in risk_result.reasons
            ):
                send_pause_trigger_alert(logger, rejected.reject_reason or "Risk rejected")
                insert_system_event(
                    config.db_path,
                    _system_event(
                        "WARNING",
                        "pause_trigger",
                        rejected.reject_reason or "Risk rejection",
                        {
                            "symbol": selected_intent.symbol,
                            "strategy_type": selected_intent.strategy_type,
                        },
                    ),
                )
            return
    elif (
        risk_result.suggested_notional is not None
        and risk_result.suggested_notional < selected_intent.target_notional_usd
    ):
        executable_intent = replace(
            selected_intent,
            target_notional_usd=round(float(risk_result.suggested_notional), 2),
        )

    log_trade_intent(logger, executable_intent)
    logger.info(
        "Execution intent %s | strategy=%s | final_notional=%s",
        executable_intent.symbol,
        executable_intent.strategy_type,
        executable_intent.target_notional_usd,
    )

    execution_result = await submit_execution_intent(
        executable_intent,
        config,
        bybit_client=bybit_client,
        hyperliquid_client=hyperliquid_client,
        db_path=config.db_path,
    )
    insert_execution_result(config.db_path, execution_result)
    log_execution_result(logger, execution_result)

    logger.info("DB path in use: %s", config.db_path)

    latest_prices = {
        symbol: {
            "bybit_price": bybit_ticker.mark_price,
            "hyperliquid_price": hyperliquid_ticker.mark_price,
        }
    }

    closed_count = await reconcile_open_paper_trades(
        db_path=config.db_path,
        latest_prices=latest_prices,
        max_hold_minutes=config.max_hold_time_minutes,
    )

    if closed_count > 0:
        logger.info("Closed %s open paper trades for %s", closed_count, symbol)

    if execution_result.accepted:
        executed = replace(selected_opportunity, decision="executed", reject_reason=None)
        insert_opportunity(config.db_path, executed)

        position_pair = build_position_pair_from_execution(executable_intent, execution_result)
        position_pair_id = insert_position_pair(config.db_path, position_pair)
        logger.info(
            "Inserted position pair id=%s for symbol=%s into db=%s",
            position_pair_id,
            position_pair.symbol,
            config.db_path,
        )
        persisted_position_pair = replace(position_pair, id=position_pair_id)
        send_trade_entered_alert(logger, persisted_position_pair)
    else:
        accepted = replace(selected_opportunity, decision="accepted", reject_reason=execution_result.reason)
        insert_opportunity(config.db_path, accepted)

    if execution_result.status == "PAPER_SKIPPED_DUPLICATE":
        logger.info(
           "Duplicate paper trade skipped | symbol=%s | strategy=%s | reason=%s",
           executable_intent.symbol,
           executable_intent.strategy_type,
           execution_result.reason,
        )
    else:
        send_one_leg_risk_alert(
           logger,
           selected_intent.symbol,
           execution_result.reason,
        )

async def process_symbol_degraded(
    config: Config,
    logger,
    symbol: str,
    bybit_client: BybitClient,
) -> None:
    bybit_ticker = await bybit_client.get_ticker(symbol)
    bybit_funding = await bybit_client.get_latest_funding_rate(symbol)
    insert_market_snapshot(
        config.db_path,
        "bybit",
        symbol,
        bybit_ticker.last_price,
        bybit_ticker.mark_price,
        bybit_ticker.index_price,
        None,
        None,
        bybit_ticker.timestamp.isoformat(),
    )
    insert_funding_snapshot(
        config.db_path,
        bybit_funding.exchange,
        symbol,
        bybit_funding.raw_rate,
        bybit_funding.interval_hours,
        bybit_funding.rate_8h_equivalent,
        bybit_funding.predicted_rate_8h_equivalent,
        None,
        bybit_funding.observed_at.isoformat(),
    )
    insert_system_event(
        config.db_path,
        _system_event(
            "INFO",
            "degraded_scan",
            f"{symbol} scanned in degraded mode",
            {"exchange": "bybit"},
        ),
    )

def log_paper_trade_summary(logger, db_path: str) -> None:
    rows = list_paper_trades(db_path)
    summary = compute_paper_trade_summary(rows)
    logger.info(
        "Paper summary | opened=%s | closed=%s | open=%s | realized_pnl_usd=%.4f | realized_pnl_bp=%.2f | win_rate=%.2f%% | avg_hold_mins=%.2f",
        summary["opened"],
        summary["closed"],
        summary["open_count"],
        summary["realized_pnl_usd"],
        summary["realized_pnl_bp"],
        summary["win_rate"] * 100.0,
        summary["average_holding_minutes"],
    )

async def scanner_loop(
    logger,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
) -> None:
    market_state = MarketStateTracker()
    started_alert_sent = False
    capital_unavailable_alerted = False

    cycle_count = 0
    while True:
        config = reload_config_if_needed()
        bybit_ok, hyperliquid_ok = await asyncio.gather(
            bybit_client.healthcheck(),
            hyperliquid_client.healthcheck(),
        )
        insert_heartbeat(config.db_path, "bybit", "ok" if bybit_ok else "failed")
        insert_heartbeat(config.db_path, "hyperliquid", "ok" if hyperliquid_ok else "failed")

        bot_state = "running" if bybit_ok and hyperliquid_ok else "paused"
        log_system_health(
            logger,
            bot_state=bot_state,
            bybit_ok=bybit_ok,
            hyperliquid_ok=hyperliquid_ok,
        )
        insert_system_event(
            config.db_path,
            _system_event(
                "INFO",
                "system_health",
                "Scanner cycle health updated",
                {
                    "bot_state": bot_state,
                    "bybit_ok": bybit_ok,
                    "hyperliquid_ok": hyperliquid_ok,
                },
            ),
        )

        if not started_alert_sent:
            send_bot_started_alert(logger)
            started_alert_sent = True

        if not bybit_ok:
            send_disconnect_alert(logger, "bybit")
        if not hyperliquid_ok:
            send_disconnect_alert(logger, "hyperliquid")

        if bybit_ok and hyperliquid_ok:
            (
                bybit_account,
                hyperliquid_account,
                bybit_fee_bp,
                hyperliquid_fee_bp,
            ) = await asyncio.gather(
                bybit_client.get_account_snapshot(),
                hyperliquid_client.get_account_snapshot(),
                bybit_client.get_maker_fee_bp(config.symbols[0] if config.symbols else None),
                hyperliquid_client.get_maker_fee_bp(),
            )
            set_live_fee_override("bybit", bybit_fee_bp)
            set_live_fee_override("hyperliquid", hyperliquid_fee_bp)
            effective_bybit_account, effective_hyperliquid_account = _apply_account_snapshot_config_overrides(
                config,
                bybit_account,
                hyperliquid_account,
            )
            account_state = combine_account_snapshots(
                effective_bybit_account,
                effective_hyperliquid_account,
            )

            logger.info(
                "Raw account snapshots | bybit_equity=%s bybit_available=%s bybit_margin_used=%s | hyper_equity=%s hyper_available=%s hyper_margin_used=%s",
                bybit_account.equity_usd,
                bybit_account.available_balance_usd,
                bybit_account.margin_used_usd,
                hyperliquid_account.equity_usd,
                hyperliquid_account.available_balance_usd,
                hyperliquid_account.margin_used_usd,
            )
            logger.info(
                "Effective account snapshots | bybit_equity=%s bybit_available=%s bybit_margin_used=%s | hyper_equity=%s hyper_available=%s hyper_margin_used=%s | paired_available=%s",
                effective_bybit_account.equity_usd,
                effective_bybit_account.available_balance_usd,
                effective_bybit_account.margin_used_usd,
                effective_hyperliquid_account.equity_usd,
                effective_hyperliquid_account.available_balance_usd,
                effective_hyperliquid_account.margin_used_usd,
                account_state.paired_available_balance_usd,
            )

            if config.pause_on_zero_effective_capital and account_state.paired_available_balance_usd <= 0:
                message = (
                    "No usable paired capital available. "
                    "Set funded exchange account addresses/keys or configure "
                    "BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD and HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD."
                )
                if not capital_unavailable_alerted:
                    logger.warning(message)
                    insert_system_event(
                        config.db_path,
                        _system_event(
                            "WARNING",
                            "capital_unavailable",
                            message,
                            {
                                "bybit_available_usd": effective_bybit_account.available_balance_usd,
                                "hyperliquid_available_usd": effective_hyperliquid_account.available_balance_usd,
                                "bybit_raw_available_usd": bybit_account.available_balance_usd,
                                "hyperliquid_raw_available_usd": hyperliquid_account.available_balance_usd,
                            },
                        ),
                    )
                    capital_unavailable_alerted = True
                if config.run_once:
                    break
                await asyncio.sleep(config.poll_interval_seconds)
                continue
            if capital_unavailable_alerted:
                logger.info("Usable paired capital restored; resuming opportunity evaluation")
                insert_system_event(
                    config.db_path,
                    _system_event(
                        "INFO",
                        "capital_restored",
                        "Usable paired capital restored; resuming opportunity evaluation",
                        {
                            "bybit_available_usd": effective_bybit_account.available_balance_usd,
                            "hyperliquid_available_usd": effective_hyperliquid_account.available_balance_usd,
                            "paired_available_usd": account_state.paired_available_balance_usd,
                        },
                    ),
                )
                capital_unavailable_alerted = False

            for symbol in config.symbols:
                try:
                    await process_symbol_full(
                        config=config,
                        logger=logger,
                        symbol=symbol,
                        bybit_client=bybit_client,
                        hyperliquid_client=hyperliquid_client,
                        account_state=account_state,
                        market_state=market_state,
                    )
                except Exception as exc:
                    insert_system_event(
                        config.db_path,
                        _system_event(
                            "ERROR",
                            "process_symbol_failure",
                            f"Failed processing {symbol}: {exc}",
                        ),
                    )
                    logger.exception("Failed processing symbol %s: %s", symbol, exc)
        else:
            clear_live_fee_overrides()
        if (not hyperliquid_ok) and config.allow_degraded_mode and bybit_ok:
            for symbol in config.symbols:
                await process_symbol_degraded(config, logger, symbol, bybit_client)

        if config.run_once:
            break

        cycle_count += 1

        if cycle_count % 12 == 0:
            log_paper_trade_summary(logger, config.db_path)
        await asyncio.sleep(config.poll_interval_seconds)


async def reconciliation_loop(
    logger,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
) -> None:
    while True:
        config = reload_config_if_needed()
        open_positions = get_open_positions(config.db_path)
        try:
            live_positions = await _build_live_positions(config, bybit_client, hyperliquid_client)
        except Exception as exc:
            insert_system_event(
                config.db_path,
                _system_event(
                    "ERROR",
                    "reconciliation_live_fetch_failure",
                    f"Failed fetching live positions: {exc}",
                ),
            )
            logger.exception("Failed fetching live positions for reconciliation: %s", exc)
            if config.run_once:
                break
            await asyncio.sleep(config.reconciliation_interval_seconds)
            continue
        events = reconcile_expected_vs_actual_positions(open_positions, live_positions)

        for position in open_positions:
            delta_imbalance_bp = compute_delta_imbalance_bp(position, live_positions)
            if delta_imbalance_bp > 10.0:
                degraded = mark_position_degraded(position, "Reconciliation mismatch")
                if degraded.id is not None:
                    update_position_pair_status(
                        config.db_path,
                        degraded.id,
                        degraded.status,
                        delta_imbalance_bp=delta_imbalance_bp,
                    )
                log_reconciliation_event(
                    logger,
                    handle_reconciliation_mismatch(position, delta_imbalance_bp),
                )
                insert_system_event(
                    config.db_path,
                    _system_event(
                        "WARNING",
                        "position_degraded",
                        f"{position.symbol} marked degraded",
                        {
                            "position_pair_id": degraded.id,
                            "delta_imbalance_bp": delta_imbalance_bp,
                        },
                    ),
                )

        for event in events:
            insert_system_event(config.db_path, event)
            log_reconciliation_event(logger, event)

        if config.run_once:
            break

        await asyncio.sleep(config.reconciliation_interval_seconds)


async def run() -> None:
    config = load_config()
    logger = configure_logger(config.log_level, config.log_path)
    initialize_database(config.db_path)
    logger.info("Runtime DB path: %s", config.db_path)

    logger.info(
        "Config debug | bybit_override=%s | hyper_override=%s | hyper_account=%s | hyper_vault=%s | pause_on_zero=%s",
        config.bybit_available_balance_override_usd,
        config.hyperliquid_available_balance_override_usd,
        config.hyperliquid_account_address,
        config.hyperliquid_vault_address,
        config.pause_on_zero_effective_capital,
    )

    bybit_client = BybitClient(
        api_key=config.bybit_api_key,
        api_secret=config.bybit_api_secret,
        is_testnet=config.is_testnet,
        base_url=config.bybit_rest_url,
        recv_window_ms=config.bybit_recv_window_ms,
        account_type=config.bybit_account_type,
        settle_coin=config.bybit_settle_coin,
    )
    hyperliquid_client = HyperliquidClient(
        private_key=config.hyperliquid_private_key,
        is_testnet=config.is_testnet,
        base_url=config.hyperliquid_rest_url,
        vault_address=config.hyperliquid_vault_address,
        account_address=config.hyperliquid_account_address,
    )

    await _perform_startup_capital_preflight(
        config,
        logger,
        bybit_client,
        hyperliquid_client,
    )

    dashboard_runner = None
    if config.dashboard_enabled:
        dashboard_runner = await run_dashboard_server(
            database_path=config.db_path,
            host=config.dashboard_host,
            port=config.dashboard_port,
            refresh_seconds=config.dashboard_refresh_seconds,
            logger=logger,
        )

    scanner_task = asyncio.create_task(
        scanner_loop(logger, bybit_client, hyperliquid_client)
    )
 #   reconciler_task = asyncio.create_task(
 #       reconciliation_loop(logger, bybit_client, hyperliquid_client)
 #   )

    try:
        await asyncio.gather(scanner_task)
    finally:
        scanner_task.cancel()
        if dashboard_runner is not None:
            await dashboard_runner.cleanup()


def main() -> None:
    try:
        asyncio.run(run())
    except StartupPreflightError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Shutdown requested; arbitrage bot stopped cleanly.")


if __name__ == "__main__":
    main()
