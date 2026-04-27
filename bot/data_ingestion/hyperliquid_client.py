from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from eth_account import Account as EthAccount

from bot.data_ingestion.account_models import AccountSnapshot
from bot.data_ingestion.funding_models import FundingRateSnapshot
from bot.data_ingestion.trading_models import OrderPlacement, OrderStatusSnapshot, PositionExposure

try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
except ImportError as exc:  # pragma: no cover - exercised only when deps are missing
    Exchange = None  # type: ignore[assignment]
    Info = None  # type: ignore[assignment]
    _HYPERLIQUID_IMPORT_ERROR = exc
else:
    _HYPERLIQUID_IMPORT_ERROR = None


@dataclass(frozen=True)
class HyperliquidTickerSnapshot:
    symbol: str
    last_price: float
    mark_price: float
    timestamp: datetime


class HyperliquidClient:
    def __init__(
        self,
        private_key: str,
        is_testnet: bool,
        base_url: str | None = None,
        vault_address: str | None = None,
        account_address: str | None = None,
    ) -> None:
        normalized_private_key = private_key if private_key.startswith("0x") else f"0x{private_key}"
        self.private_key = normalized_private_key
        self.is_testnet = is_testnet
        self.base_url = base_url or (
            "https://api.hyperliquid-testnet.xyz"
            if is_testnet
            else "https://api.hyperliquid.xyz"
        )
        self.vault_address = vault_address.lower() if vault_address else None
        self.account_address = account_address.lower() if account_address else None
        self._wallet = EthAccount.from_key(self.private_key)
        self.wallet_address = self._wallet.address.lower()
        self._info = None
        self._exchange = None
        self._resolved_user_address: str | None = (
            (self.vault_address or self.account_address).lower()
            if (self.vault_address or self.account_address)
            else None
        )
        self._resolved_user_role: str | None = None
        print("DEBUG Hyperliquid signer wallet:", self.wallet_address)
        print("DEBUG Hyperliquid resolved user:", self._resolved_user_address)

    @staticmethod
    def _to_hl_coin(symbol: str) -> str:
        normalized_symbol = symbol.upper()
        if normalized_symbol.endswith("USDT"):
            return normalized_symbol[:-4]
        return normalized_symbol

    async def healthcheck(self) -> bool:
        url = f"{self.base_url}/info"
        body = {"type": "allMids"}
        for attempt in range(5):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=body, timeout=10) as response:
                        if response.status != 200:
                            await asyncio.sleep(2 + attempt)
                            continue
                        payload = await response.json()
                        if isinstance(payload, dict) and len(payload) > 0:
                            return True
            except Exception:
                await asyncio.sleep(2 + attempt)
        return False

    async def get_ticker(self, symbol: str) -> HyperliquidTickerSnapshot:
        url = f"{self.base_url}/info"
        body = {"type": "allMids"}
        coin = self._to_hl_coin(symbol)

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=body, timeout=10) as response:
                        response.raise_for_status()
                        payload = await response.json()

                if coin not in payload:
                    raise ValueError(
                        f"No Hyperliquid mid returned for coin {coin}. "
                        f"Response keys sample: {list(payload.keys())[:10]}"
                    )

                price = float(payload[coin])
                return HyperliquidTickerSnapshot(
                    symbol=symbol.upper(),
                    last_price=price,
                    mark_price=price,
                    timestamp=datetime.now(timezone.utc),
                )
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1 + attempt)

        raise RuntimeError(
            f"Hyperliquid get_ticker failed for {symbol} after retries: {last_error}"
        )

    async def get_latest_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        coin = self._to_hl_coin(symbol)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)

        url = f"{self.base_url}/info"
        body = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(now.timestamp() * 1000),
        }

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=body, timeout=10) as response:
                        response.raise_for_status()
                        payload = await response.json()

                if not isinstance(payload, list) or not payload:
                    raise ValueError(
                        f"No Hyperliquid funding history returned for coin {coin}: {payload}"
                    )

                latest = payload[-1]
                raw_rate = float(
                    latest.get("fundingRate")
                    or latest.get("funding")
                    or latest.get("rate")
                )
                ts_ms = int(
                    latest.get("time")
                    or latest.get("fundingTime")
                    or latest.get("timestamp")
                )
                observed_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                return FundingRateSnapshot(
                    exchange="hyperliquid",
                    symbol=symbol.upper(),
                    raw_rate=raw_rate,
                    interval_hours=1.0,
                    rate_8h_equivalent=raw_rate * 8.0,
                    observed_at=observed_at,
                    predicted_rate_8h_equivalent=raw_rate * 8.0,
                )
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1 + attempt)

        raise RuntimeError(
            f"Hyperliquid get_latest_funding_rate failed for {symbol} after retries: {last_error}"
        )

    async def get_account_snapshot(self) -> AccountSnapshot:
        info, _ = await self._ensure_sdk_clients()
        user_address = await self.resolve_user_address()
        state = await asyncio.to_thread(info.user_state, user_address)
        margin_summary = state.get("marginSummary") or state.get("crossMarginSummary") or {}
        return AccountSnapshot(
            exchange="hyperliquid",
            equity_usd=self._safe_float(margin_summary.get("accountValue")),
            available_balance_usd=self._extract_available_balance_usd(state),
            margin_used_usd=self._safe_float(margin_summary.get("totalMarginUsed")),
        )

    async def get_orderbook_depth_usd(self, symbol: str) -> float:
        coin = self._to_hl_coin(symbol)
        url = f"{self.base_url}/info"
        body = {"type": "l2Book", "coin": coin}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=10) as response:
                response.raise_for_status()
                payload = await response.json()

        levels = self._extract_book_levels(payload)
        total_depth = 0.0
        for side_levels in levels:
            for level in side_levels:
                price = float(level.get("px") or level.get("price"))
                size = float(level.get("sz") or level.get("size"))
                total_depth += price * size
        return total_depth

    async def get_maker_fee_bp(self) -> float | None:
        try:
            info, _ = await self._ensure_sdk_clients()
            fees = await asyncio.to_thread(info.user_fees, await self.resolve_user_address())
            user_add_rate = fees.get("userAddRate")
            if user_add_rate is None:
                return None
            return float(user_add_rate) * 10_000
        except Exception:
            return None

    async def get_position_exposures(
        self,
        symbols: list[str] | None = None,
    ) -> list[PositionExposure]:
        info, _ = await self._ensure_sdk_clients()
        state = await asyncio.to_thread(info.user_state, await self.resolve_user_address())
        requested_symbols = {symbol.upper() for symbol in symbols} if symbols else None
        exposures: list[PositionExposure] = []

        for asset_position in state.get("assetPositions", []):
            position = asset_position.get("position", {})
            symbol = f'{position.get("coin", "").upper()}USDT'
            if requested_symbols is not None and symbol not in requested_symbols:
                continue
            side = "Buy" if float(position.get("szi") or 0.0) > 0 else "Sell"
            size = abs(float(position.get("szi") or 0.0))
            if size <= 0:
                continue
            exposures.append(
                PositionExposure(
                    exchange="hyperliquid",
                    symbol=symbol,
                    side=side,
                    size=size,
                    entry_price=float(position.get("entryPx") or 0.0),
                    notional_usd=abs(float(position.get("positionValue") or 0.0)),
                    unrealized_pnl_usd=float(position.get("unrealizedPnl") or 0.0),
                )
            )
        return exposures

    async def get_position_notionals(
        self,
        symbols: list[str] | None = None,
    ) -> dict[str, float]:
        notionals: dict[str, float] = {}
        for exposure in await self.get_position_exposures(symbols):
            notionals[exposure.symbol] = notionals.get(exposure.symbol, 0.0) + exposure.notional_usd
        return notionals

    async def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        *,
        time_in_force: str,
        reduce_only: bool = False,
    ) -> OrderPlacement:
        _, exchange = await self._ensure_sdk_clients()
        coin = self._to_hl_coin(symbol)
        rounded_size = await self.round_size(symbol, size)
        rounded_price = await self.round_price(symbol, price)

        is_buy = side == "Buy"
        payload = await asyncio.to_thread(
            exchange.order,
            coin,
            is_buy,
            rounded_size,
            rounded_price,
            {"limit": {"tif": time_in_force}},
            reduce_only,
        )

        if isinstance(payload, dict) and payload.get("status") == "err":
            err = payload.get("response")
            if isinstance(err, str) and "Too many cumulative requests sent" in err:
                return PlacementResult(
                    success=False,
                    order_id="",
                    status="REJECTED",
                    reason=f"Hyperliquid request quota exceeded: {err}",
                    average_fill_price=0.0,
                    filled_size=0.0,
                    raw_response=response,
                )

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected Hyperliquid order response type: {type(payload).__name__} | payload={payload}"
            )

        response_obj = payload.get("response", {})
        if not isinstance(response_obj, dict):
            raise RuntimeError(
                f"Unexpected Hyperliquid response field type: {type(response_obj).__name__} | payload={payload}"
            )

        data_obj = response_obj.get("data", {})
        if not isinstance(data_obj, dict):
            raise RuntimeError(
                f"Unexpected Hyperliquid data field type: {type(data_obj).__name__} | payload={payload}"
            )

        statuses = data_obj.get("statuses", [])
        first_status = statuses[0] if statuses else {}
        order_id = ""
        status = "ERROR"

        if "resting" in first_status:
            order_id = str(first_status["resting"]["oid"])
            status = "OPEN"
        elif "filled" in first_status:
            order_id = str(first_status["filled"]["oid"])
            status = "FILLED"
        elif "error" in first_status:
            status = "REJECTED"

        return OrderPlacement(
            exchange="hyperliquid",
            symbol=symbol.upper(),
            order_id=order_id,
            client_order_id=None,
            status=status,
            raw=payload,
        )

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        *,
        reduce_only: bool = False,
    ) -> OrderPlacement:
        return await self.place_order(
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            time_in_force="Alo",
            reduce_only=reduce_only,
        )

    async def place_ioc_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        *,
        reduce_only: bool = False,
    ) -> OrderPlacement:
        return await self.place_order(
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            time_in_force="Ioc",
            reduce_only=reduce_only,
        )

    async def get_order_status(self, symbol: str, order_id: str) -> OrderStatusSnapshot:
        if not order_id:
            return OrderStatusSnapshot(
                exchange="hyperliquid",
                symbol=symbol.upper(),
                order_id="",
                status="REJECTED",
                side=None,
                average_fill_price=None,
                filled_size=0.0,
            )

        info, _ = await self._ensure_sdk_clients()
        raw_status = await asyncio.to_thread(
            info.query_order_by_oid,
            await self.resolve_user_address(),
            int(order_id),
        )
        wrapper = raw_status.get("order", {})
        order = wrapper.get("order", {})
        fills = await self._recent_fills_by_oid(int(order_id))

        filled_size = sum(float(fill.get("sz") or 0.0) for fill in fills)
        average_fill_price = None
        if fills:
            total_notional = sum(float(fill.get("sz") or 0.0) * float(fill.get("px") or 0.0) for fill in fills)
            if filled_size > 0:
                average_fill_price = total_notional / filled_size
        elif order.get("limitPx") is not None:
            average_fill_price = float(order["limitPx"])

        if filled_size == 0 and order:
            original_size = float(order.get("origSz") or 0.0)
            open_size = float(order.get("sz") or 0.0)
            filled_size = max(original_size - open_size, 0.0)

        return OrderStatusSnapshot(
            exchange="hyperliquid",
            symbol=symbol.upper(),
            order_id=order_id,
            status=self._normalize_order_status(wrapper.get("status") or "UNKNOWN"),
            side=self._normalize_side(order.get("side")),
            average_fill_price=average_fill_price,
            filled_size=filled_size,
            raw=raw_status,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if not order_id:
            return {"status": "skipped", "reason": "missing_order_id"}
        _, exchange = await self._ensure_sdk_clients()
        return await asyncio.to_thread(exchange.cancel, self._to_hl_coin(symbol), int(order_id))

    async def round_size(self, symbol: str, size: float) -> float:
        info, _ = await self._ensure_sdk_clients()
        decimals = info.asset_to_sz_decimals[info.name_to_asset(self._to_hl_coin(symbol))]
        return round(size, decimals)

    @staticmethod
    def round_price(price: float) -> float:
        return round(price, 6)

    async def _recent_fills_by_oid(self, order_id: int) -> list[dict[str, Any]]:
        info, _ = await self._ensure_sdk_clients()
        fills = await asyncio.to_thread(info.user_fills, await self.resolve_user_address())
        return [fill for fill in fills if int(fill.get("oid") or -1) == order_id]

    async def resolve_user_address(self) -> str:
        if self._resolved_user_address is not None:
            return self._resolved_user_address

        info = await self._ensure_info_client()
        role_payload = await asyncio.to_thread(info.user_role, self.wallet_address)
        role = str(role_payload.get("role") or "missing")
        self._resolved_user_role = role

        if role == "agent":
            resolved_address = str((role_payload.get("data") or {}).get("user") or self.wallet_address)
        else:
            resolved_address = self.wallet_address

        self._resolved_user_address = resolved_address.lower()
        return self._resolved_user_address

    async def round_price(self, symbol: str, price: float) -> float:
        print("HL NEW round_price called", symbol, price)

        info, _ = await self._ensure_sdk_clients()
        coin = self._to_hl_coin(symbol)
        asset = info.name_to_asset(coin)

        meta = None
        if hasattr(info, "meta"):
            try:
                meta = await asyncio.to_thread(info.meta)
                print("HL RAW META", meta)
            except Exception as exc:
                print("HL round_price meta fetch failed", exc)
                meta = None

        tick_size = None
        price_decimals = None

        if isinstance(meta, dict):
            universe = meta.get("universe") or meta.get("assets") or []
            if isinstance(universe, list) and 0 <= asset < len(universe):
                asset_meta = universe[asset]
                print("HL ASSET META", {"asset": asset, "asset_meta": asset_meta})
        if isinstance(asset_meta, dict):
                    tick_size = asset_meta.get("tickSize") or asset_meta.get("pxTick")
                    price_decimals = asset_meta.get("priceDecimals") or asset_meta.get("pxDecimals")

        print(
            "HL round_price debug",
            {
                "symbol": symbol,
                "coin": coin,
                "asset": asset,
                "tick_size": tick_size,
                "price_decimals": price_decimals,
                "input_price": price,
            },
        )

        if tick_size is not None:
            tick = float(tick_size)
            if tick > 0:
                snapped = round(price / tick) * tick
                decimals = 0
                tick_text = f"{tick:.12f}".rstrip("0")
                if "." in tick_text:
                    decimals = len(tick_text.split(".")[1])
                final_price = round(snapped, decimals)
                print("HL round_price snapped via tick", final_price)
                return final_price

        if price_decimals is not None:
            final_price = round(price, int(price_decimals))
            print("HL round_price snapped via decimals", final_price)
            return final_price

        fallback_price = round(price, 6)
        print("HL round_price fallback", fallback_price)
        return fallback_price    


    async def resolve_user_identity(self) -> tuple[str, str]:
        resolved_address = await self.resolve_user_address()
        resolved_role = self._resolved_user_role or (
            "configured" if (self.account_address or self.vault_address) else "unknown"
        )
        return resolved_address, resolved_role

    async def _ensure_sdk_clients(self):
        if _HYPERLIQUID_IMPORT_ERROR is not None or Info is None or Exchange is None:
            raise RuntimeError(
                "hyperliquid-python-sdk is required for live Hyperliquid trading"
            ) from _HYPERLIQUID_IMPORT_ERROR
        info = await self._ensure_info_client()
        if self._exchange is None:
            resolved_user_address = await self.resolve_user_address()

            def _build_exchange():
                return Exchange(
                    self._wallet,
                    base_url=self.base_url,
                    vault_address=self.vault_address,
                    account_address=(
                        self.account_address
                        or (resolved_user_address if self._resolved_user_role == "agent" else None)
                    ),
                )

            self._exchange = await asyncio.to_thread(_build_exchange)
        self._info = info
        return self._info, self._exchange

    async def _ensure_info_client(self):
        if _HYPERLIQUID_IMPORT_ERROR is not None or Info is None:
            raise RuntimeError(
                "hyperliquid-python-sdk is required for live Hyperliquid trading"
            ) from _HYPERLIQUID_IMPORT_ERROR
        if self._info is not None:
            return self._info

        def _build_info():
            return Info(self.base_url, skip_ws=True)

        self._info = await asyncio.to_thread(_build_info)
        return self._info

    @classmethod
    def _extract_available_balance_usd(cls, state: dict[str, Any]) -> float:
        withdrawable = cls._safe_float(state.get("withdrawable"))
        if withdrawable > 0:
            return withdrawable

        margin_summary = state.get("marginSummary") or {}
        cross_margin_summary = state.get("crossMarginSummary") or {}
        summary_candidates = [margin_summary, cross_margin_summary]

        derived_candidates = [
            max(
                cls._safe_float(summary.get("accountValue"))
                - cls._safe_float(summary.get("totalMarginUsed")),
                0.0,
            )
            for summary in summary_candidates
            if isinstance(summary, dict)
        ]

        asset_position_upl = sum(
            max(cls._safe_float((asset_position.get("position") or {}).get("unrealizedPnl")), 0.0)
            for asset_position in state.get("assetPositions", [])
            if isinstance(asset_position, dict)
        )

        return max([0.0, *derived_candidates, asset_position_upl])

    @staticmethod
    def _safe_float(value: Any) -> float:
        if value in {None, ""}:
            return 0.0
        return float(value)

    @staticmethod
    def _normalize_side(side: str | None) -> str | None:
        if side == "B":
            return "Buy"
        if side == "A":
            return "Sell"
        return side

    @staticmethod
    def _normalize_order_status(status: str) -> str:
        normalized = status.strip().upper()
        mapping = {
            "OPEN": "OPEN",
            "TRIGGERED": "OPEN",
            "FILLED": "FILLED",
            "CANCELED": "CANCELED",
            "MARGINCANCELED": "REJECTED",
            "REJECTED": "REJECTED",
        }
        return mapping.get(normalized, normalized)

    @staticmethod
    def _extract_book_levels(payload: Any) -> list[list[dict[str, Any]]]:
        if isinstance(payload, dict) and isinstance(payload.get("levels"), list):
            return payload["levels"]

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and isinstance(item.get("levels"), list):
                    return item["levels"]

        raise ValueError(f"Unexpected Hyperliquid orderbook payload: {payload}")
