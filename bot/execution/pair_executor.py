from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from bot.execution.paper_executor import execute_paper_pair

from bot.config.config import Config
from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient
from bot.data_ingestion.trading_models import OrderPlacement, OrderStatusSnapshot
from bot.execution.models import ExecutionResult, LegExecutionResult
from bot.signal_generator.models import TradeIntent


async def execute_delta_neutral_pair(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient | None = None,
    hyperliquid_client: HyperliquidClient | None = None,
    db_path: str | None = None,
) -> ExecutionResult:
    if bybit_client is None or hyperliquid_client is None:
        return _execute_stub_pair(intent, config)

    bybit_price = float(intent.metadata.get("bybit_price") or 0.0)
    hyperliquid_price = float(intent.metadata.get("hyperliquid_price") or 0.0)

    if not LIVE_EXECUTION_ENABLED:
        if db_path is None:
            return ExecutionResult(
                symbol=intent.symbol,
                strategy_type=intent.strategy_type,
                status="PAPER_ONLY",
                accepted=False,
                reason="Live execution disabled and no DB path available for paper execution",
                bybit_leg=LegExecutionResult(
                    exchange="bybit",
                    side=intent.bybit_side,
                    order_id="",
                    requested_notional_usd=intent.target_notional_usd,
                    filled_notional_usd=0.0,
                    average_fill_price=0.0,
                    status="SKIPPED",
                    reason="Paper execution unavailable",
                ),
                hyperliquid_leg=LegExecutionResult(
                    exchange="hyperliquid",
                    side=intent.hyperliquid_side,
                    order_id="",
                    requested_notional_usd=intent.target_notional_usd,
                    filled_notional_usd=0.0,
                    average_fill_price=0.0,
                    status="SKIPPED",
                    reason="Paper execution unavailable",
                ),
                created_at=datetime.now(timezone.utc),
                metadata={"mode": "paper"},
            )

        total_cost_bp = float(intent.gross_expected_bp - intent.expected_net_bp)

        return await execute_paper_pair(
            intent=intent,
            bybit_price=bybit_price,
            hyperliquid_price=hyperliquid_price,
            db_path=db_path,
            total_cost_bp=total_cost_bp,
        )

    if bybit_price <= 0 or hyperliquid_price <= 0:
       return _build_execution_result(
           intent,
           accepted=False,
           status="LEG_FAILURE",
           reason="Missing reference prices for live execution",
           bybit_leg=LegExecutionResult(
              exchange="bybit",
              side=intent.bybit_side,
              order_id="",
              requested_notional_usd=intent.target_notional_usd,
              filled_notional_usd=0.0,
              average_fill_price=0.0,
              status="REJECTED",
              reason="Missing Bybit reference price",
           ),
           hyperliquid_leg=LegExecutionResult(
              exchange="hyperliquid",
              side=intent.hyperliquid_side,
              order_id="",
              requested_notional_usd=intent.target_notional_usd,
              filled_notional_usd=0.0,
              average_fill_price=0.0,
              status="REJECTED",
              reason="Missing Hyperliquid reference price",
           ),
       )

    bybit_leg = await _safe_place_bybit_leg(intent, config, bybit_client, bybit_price)
    hyperliquid_leg = await _safe_place_hyperliquid_leg(intent, config, hyperliquid_client, hyperliquid_price)

    print("DEBUG Bybit leg:", bybit_leg)
    print("DEBUG Hyperliquid leg:", hyperliquid_leg)

    if bybit_leg.status == "REJECTED" or hyperliquid_leg.status == "REJECTED":
        return await handle_one_leg_failure(
            intent,
            config,
            bybit_client,
            hyperliquid_client,
            bybit_leg,
            hyperliquid_leg,
        )

    if not bybit_leg.order_id or not hyperliquid_leg.order_id:
        return _build_execution_result(
            intent,
            accepted=False,
            status="LEG_FAILURE",
            reason="One or both legs missing order ids after placement",
            bybit_leg=bybit_leg,
            hyperliquid_leg=hyperliquid_leg,
        )

    final_bybit_status, final_hyperliquid_status = await _poll_for_final_status(
        intent,
        config,
        bybit_client,
        hyperliquid_client,
        bybit_leg.order_id,
        hyperliquid_leg.order_id,
    )

    final_bybit_leg = _status_to_leg_result(
        exchange="bybit",
        side=intent.bybit_side,
        requested_notional_usd=intent.target_notional_usd,
        status=final_bybit_status,
        fallback_price=bybit_price,
    )
    final_hyperliquid_leg = _status_to_leg_result(
        exchange="hyperliquid",
        side=intent.hyperliquid_side,
        requested_notional_usd=intent.target_notional_usd,
        status=final_hyperliquid_status,
        fallback_price=hyperliquid_price,
    )

    if final_bybit_status.is_filled and final_hyperliquid_status.is_filled:
        return _build_execution_result(
            intent,
            accepted=True,
            status="ACCEPTED",
            reason="Both hedge legs filled",
            bybit_leg=final_bybit_leg,
            hyperliquid_leg=final_hyperliquid_leg,
            metadata={
                "execution_mode": "live",
                "bybit_order_id": bybit_leg.order_id,
                "hyperliquid_order_id": hyperliquid_leg.order_id,
            },
        )

    return await handle_partial_fill(
        intent,
        config,
        bybit_client,
        hyperliquid_client,
        final_bybit_leg,
        final_hyperliquid_leg,
    )

LIVE_EXECUTION_ENABLED = os.getenv("LIVE_EXECUTION_ENABLED", "false").strip().lower() == "true"

async def place_bybit_leg(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    reference_price: float,
) -> LegExecutionResult:
    instrument = await bybit_client.get_instrument_meta(intent.symbol)

    lot_filter = instrument.get("lotSizeFilter", {})
    price_filter = instrument.get("priceFilter", {})

    qty_step = float(lot_filter.get("qtyStep") or 0.0)
    min_qty = float(lot_filter.get("minOrderQty") or qty_step or 0.0)
    tick_size = float(price_filter.get("tickSize") or 0.0)

    raw_qty = intent.target_notional_usd / reference_price
    qty = _round_down_to_step(raw_qty, qty_step)

    if qty <= 0:
        return LegExecutionResult(
            exchange="bybit",
            side=intent.bybit_side,
            order_id="",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=0.0,
            average_fill_price=0.0,
            status="REJECTED",
            reason="Bybit quantity rounded to zero",
        )

    if min_qty > 0 and qty < min_qty:
        return LegExecutionResult(
            exchange="bybit",
            side=intent.bybit_side,
            order_id="",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=0.0,
            average_fill_price=0.0,
            status="REJECTED",
            reason=f"Bybit quantity below minimum: {qty} < {min_qty}",
        )

    price = _post_only_price(reference_price, intent.bybit_side, tick_size)

    placement = await bybit_client.place_limit_order(
        symbol=intent.symbol,
        side=intent.bybit_side,
        qty=qty,
        price=price,
        order_link_id=f"bybit-{uuid4().hex[:18]}",
    )
    return _placement_to_leg_result(
        exchange="bybit",
        side=intent.bybit_side,
        requested_notional_usd=intent.target_notional_usd,
        placement=placement,
        fallback_price=price,
    )


async def place_hyperliquid_leg(
    intent: TradeIntent,
    config: Config,
    hyperliquid_client: HyperliquidClient,
    reference_price: float,
) -> LegExecutionResult:
    raw_size = intent.target_notional_usd / reference_price
    size = await hyperliquid_client.round_size(intent.symbol, raw_size)

    if size <= 0:
        return LegExecutionResult(
            exchange="hyperliquid",
            side=intent.hyperliquid_side,
            order_id="",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=0.0,
            average_fill_price=0.0,
            status="REJECTED",
            reason="Hyperliquid size rounded to zero",
        )

    placement = await hyperliquid_client.place_limit_order(
        symbol=intent.symbol,
        side=intent.hyperliquid_side,
        size=size,
        price=reference_price,
    )
    return _placement_to_leg_result(
        exchange="hyperliquid",
        side=intent.hyperliquid_side,
        requested_notional_usd=intent.target_notional_usd,
        placement=placement,
        fallback_price=reference_price,
    )

async def _safe_place_bybit_leg(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    reference_price: float,
) -> LegExecutionResult:
    try:
        return await place_bybit_leg(intent, config, bybit_client, reference_price)
    except Exception as exc:
        return LegExecutionResult(
            exchange="bybit",
            side=intent.bybit_side,
            order_id="",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=0.0,
            average_fill_price=0.0,
            status="REJECTED",
            reason=str(exc),
        )
async def _safe_place_hyperliquid_leg(
    intent: TradeIntent,
    config: Config,
    hyperliquid_client: HyperliquidClient,
    reference_price: float,
) -> LegExecutionResult:
    try:
        return await place_hyperliquid_leg(intent, config, hyperliquid_client, reference_price)
    except Exception as exc:
        return LegExecutionResult(
            exchange="hyperliquid",
            side=intent.hyperliquid_side,
            order_id="",
            requested_notional_usd=intent.target_notional_usd,
            filled_notional_usd=0.0,
            average_fill_price=0.0,
            status="REJECTED",
            reason=str(exc),
        )
    
def _round_hyperliquid_price(price: float) -> float:
    if price >= 100000:
        return round(price, 0)
    if price >= 10000:
        return round(price, 1)
    if price >= 1000:
        return round(price, 2)
    if price >= 100:
        return round(price, 3)
    if price >= 10:
        return round(price, 4)
    return round(price, 5)

async def handle_partial_fill(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    bybit_leg: LegExecutionResult,
    hyperliquid_leg: LegExecutionResult,
) -> ExecutionResult:
    cancel_results = await cancel_outstanding_orders(
        intent,
        bybit_client,
        hyperliquid_client,
        bybit_leg.order_id,
        hyperliquid_leg.order_id,
    )
    unwind_result = await emergency_unwind_exposed_leg(
        intent,
        config,
        bybit_client,
        hyperliquid_client,
        bybit_leg,
        hyperliquid_leg,
    )
    return _build_execution_result(
        intent,
        accepted=False,
        status="PARTIAL_FILL",
        reason="One or more legs did not fully fill; outstanding orders were cancelled and exposure was unwound",
        bybit_leg=bybit_leg,
        hyperliquid_leg=hyperliquid_leg,
        metadata={
            "execution_mode": "live",
            "cancel_results": cancel_results,
            "unwind_result": unwind_result,
        },
    )


async def handle_one_leg_failure(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    bybit_leg: LegExecutionResult,
    hyperliquid_leg: LegExecutionResult,
) -> ExecutionResult:
    cancel_results = await cancel_outstanding_orders(
        intent,
        bybit_client,
        hyperliquid_client,
        bybit_leg.order_id,
        hyperliquid_leg.order_id,
    )
    unwind_result = await emergency_unwind_exposed_leg(
        intent,
        config,
        bybit_client,
        hyperliquid_client,
        bybit_leg,
        hyperliquid_leg,
    )
    return _build_execution_result(
        intent,
        accepted=False,
        status="LEG_FAILURE",
        reason="Failed to place or maintain one or both hedge legs",
        bybit_leg=bybit_leg,
        hyperliquid_leg=hyperliquid_leg,
        metadata={
            "execution_mode": "live",
            "cancel_results": cancel_results,
            "unwind_result": unwind_result,
        },
    )


async def cancel_outstanding_orders(
    intent: TradeIntent,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    bybit_order_id: str | None = None,
    hyperliquid_order_id: str | None = None,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    if bybit_order_id:
        try:
            results["bybit"] = await bybit_client.cancel_order(intent.symbol, bybit_order_id)
        except Exception as exc:  # pragma: no cover - exercised in live environments
            results["bybit"] = {"status": "error", "message": str(exc)}
    if hyperliquid_order_id:
        try:
            results["hyperliquid"] = await hyperliquid_client.cancel_order(intent.symbol, hyperliquid_order_id)
        except Exception as exc:  # pragma: no cover - exercised in live environments
            results["hyperliquid"] = {"status": "error", "message": str(exc)}
    return results


async def emergency_unwind_exposed_leg(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    bybit_leg: LegExecutionResult,
    hyperliquid_leg: LegExecutionResult,
) -> dict[str, dict]:
    unwind_results: dict[str, dict] = {}
    bybit_price = float(intent.metadata.get("bybit_price") or 0.0)
    hyperliquid_price = float(intent.metadata.get("hyperliquid_price") or 0.0)

    if bybit_leg.filled_notional_usd > 0 and bybit_price > 0:
        instrument = await bybit_client.get_instrument_meta(intent.symbol)
        qty_step = float(instrument["lotSizeFilter"]["qtyStep"])
        tick_size = float(instrument["priceFilter"]["tickSize"])
        filled_qty = _round_down_to_step(bybit_leg.filled_notional_usd / bybit_price, qty_step)
        unwind_side = _opposite_side(bybit_leg.side)
        unwind_price = _ioc_price(bybit_price, unwind_side, tick_size)
        try:
            unwind_results["bybit"] = (
                await bybit_client.place_ioc_order(
                    symbol=intent.symbol,
                    side=unwind_side,
                    qty=filled_qty,
                    price=unwind_price,
                    reduce_only=True,
                    order_link_id=f"bybit-unwind-{uuid4().hex[:12]}",
                )
            ).raw
        except Exception as exc:  # pragma: no cover - exercised in live environments
            unwind_results["bybit"] = {"status": "error", "message": str(exc)}

    if hyperliquid_leg.filled_notional_usd > 0 and hyperliquid_price > 0:
        filled_size = await hyperliquid_client.round_size(
            intent.symbol,
            hyperliquid_leg.filled_notional_usd / hyperliquid_price,
        )
        unwind_side = _opposite_side(hyperliquid_leg.side)
        unwind_price = _ioc_price(hyperliquid_price, unwind_side, _relative_tick(hyperliquid_price))
        try:
            unwind_results["hyperliquid"] = (
                await hyperliquid_client.place_ioc_order(
                    symbol=intent.symbol,
                    side=unwind_side,
                    size=filled_size,
                    price=unwind_price,
                    reduce_only=True,
                )
            ).raw
        except Exception as exc:  # pragma: no cover - exercised in live environments
            unwind_results["hyperliquid"] = {"status": "error", "message": str(exc)}

    return unwind_results


async def _poll_for_final_status(
    intent: TradeIntent,
    config: Config,
    bybit_client: BybitClient,
    hyperliquid_client: HyperliquidClient,
    bybit_order_id: str,
    hyperliquid_order_id: str,
) -> tuple[OrderStatusSnapshot, OrderStatusSnapshot]:
    deadline = asyncio.get_running_loop().time() + config.execution_order_timeout_seconds
    bybit_status = await bybit_client.get_order_status(intent.symbol, bybit_order_id)
    hyperliquid_status = await hyperliquid_client.get_order_status(intent.symbol, hyperliquid_order_id)

    while asyncio.get_running_loop().time() < deadline:
        if bybit_status.is_filled and hyperliquid_status.is_filled:
            return bybit_status, hyperliquid_status
        if bybit_status.is_rejected or hyperliquid_status.is_rejected:
            return bybit_status, hyperliquid_status
        await asyncio.sleep(config.execution_status_poll_interval_seconds)
        bybit_status, hyperliquid_status = await asyncio.gather(
            bybit_client.get_order_status(intent.symbol, bybit_order_id),
            hyperliquid_client.get_order_status(intent.symbol, hyperliquid_order_id),
        )

    return bybit_status, hyperliquid_status


def _execute_stub_pair(intent: TradeIntent, config: Config) -> ExecutionResult:
    bybit_leg = LegExecutionResult(
        exchange="bybit",
        side=intent.bybit_side,
        order_id=f"bybit-{uuid4().hex[:12]}",
        requested_notional_usd=intent.target_notional_usd,
        filled_notional_usd=intent.target_notional_usd,
        average_fill_price=float(intent.metadata.get("bybit_price", 0.0)),
        status="FILLED",
        reason="Stub Bybit leg acknowledged",
    )
    hyperliquid_leg = LegExecutionResult(
        exchange="hyperliquid",
        side=intent.hyperliquid_side,
        order_id=f"hl-{uuid4().hex[:12]}",
        requested_notional_usd=intent.target_notional_usd,
        filled_notional_usd=intent.target_notional_usd,
        average_fill_price=float(intent.metadata.get("hyperliquid_price", 0.0)),
        status="FILLED",
        reason="Stub Hyperliquid leg acknowledged",
    )
    return _build_execution_result(
        intent,
        accepted=True,
        status="ACCEPTED",
        reason="Stub pair executor hedged both legs",
        bybit_leg=bybit_leg,
        hyperliquid_leg=hyperliquid_leg,
        metadata={
            "execution_mode": "stub",
            "max_hold_minutes": config.max_hold_minutes,
        },
    )


def _placement_to_leg_result(
    exchange: str,
    side: str,
    requested_notional_usd: float,
    placement: OrderPlacement,
    fallback_price: float,
) -> LegExecutionResult:
    return LegExecutionResult(
        exchange=exchange,
        side=side,
        order_id=placement.order_id,
        requested_notional_usd=requested_notional_usd,
        filled_notional_usd=0.0,
        average_fill_price=fallback_price,
        status=placement.status,
        reason=_placement_reason(placement),
    )


def _status_to_leg_result(
    exchange: str,
    side: str,
    requested_notional_usd: float,
    status: OrderStatusSnapshot,
    fallback_price: float,
) -> LegExecutionResult:
    average_fill_price = status.average_fill_price or fallback_price
    filled_notional_usd = status.filled_size * average_fill_price if average_fill_price > 0 else 0.0
    return LegExecutionResult(
        exchange=exchange,
        side=side,
        order_id=status.order_id,
        requested_notional_usd=requested_notional_usd,
        filled_notional_usd=filled_notional_usd,
        average_fill_price=average_fill_price,
        status=status.status,
        reason=_status_reason(status),
    )


def _build_execution_result(
    intent: TradeIntent,
    *,
    accepted: bool,
    status: str,
    reason: str,
    bybit_leg: LegExecutionResult,
    hyperliquid_leg: LegExecutionResult,
    metadata: dict | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        symbol=intent.symbol,
        strategy_type=intent.strategy_type,
        status=status,
        accepted=accepted,
        reason=reason,
        bybit_leg=bybit_leg,
        hyperliquid_leg=hyperliquid_leg,
        created_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )


def _placement_reason(placement: OrderPlacement) -> str:
    statuses = placement.raw.get("response", {}).get("data", {}).get("statuses", [])
    if statuses:
        first_status = statuses[0]
        if isinstance(first_status, dict) and "error" in first_status:
            return str(first_status["error"])
    return placement.status


def _status_reason(status: OrderStatusSnapshot) -> str:
    if status.exchange == "hyperliquid":
        wrapper = status.raw.get("order", {})
        raw_status = wrapper.get("status")
        if raw_status:
            return str(raw_status)
    if status.exchange == "bybit":
        raw_status = status.raw.get("orderStatus")
        if raw_status:
            return str(raw_status)
    return status.status


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    precision = max(len(f"{step:.12f}".rstrip("0").split(".")[1]) if "." in f"{step:.12f}".rstrip("0") else 0, 0)
    floored = int(value / step) * step
    return round(floored, precision)


def _post_only_price(reference_price: float, side: str, tick_size: float) -> float:
    if side == "Buy":
        return max(reference_price - tick_size, tick_size)
    return reference_price + tick_size


def _ioc_price(reference_price: float, side: str, tick_size: float) -> float:
    if side == "Buy":
        return reference_price + (tick_size * 5)
    return max(reference_price - (tick_size * 5), tick_size)


def _relative_tick(reference_price: float) -> float:
    return max(reference_price * 0.0001, 0.000001)


def _opposite_side(side: str) -> str:
    return "Sell" if side == "Buy" else "Buy"
