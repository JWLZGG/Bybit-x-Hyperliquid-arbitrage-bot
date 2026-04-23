from __future__ import annotations

import asyncio

from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient


def test_bybit_uses_total_available_balance_when_present() -> None:
    wallet = {
        "totalAvailableBalance": "125.5",
        "totalMarginBalance": "200.0",
        "totalInitialMargin": "50.0",
        "coin": [],
    }

    assert BybitClient._extract_available_balance_usd(wallet) == 125.5


def test_bybit_falls_back_to_margin_balance_minus_initial_margin() -> None:
    wallet = {
        "totalAvailableBalance": "",
        "totalMarginBalance": "210.0",
        "totalInitialMargin": "40.0",
        "coin": [],
    }

    assert BybitClient._extract_available_balance_usd(wallet) == 170.0


def test_bybit_falls_back_to_coin_level_available_value() -> None:
    wallet = {
        "totalAvailableBalance": "0",
        "totalMarginBalance": "0",
        "totalInitialMargin": "0",
        "coin": [
            {
                "coin": "USDT",
                "availableToWithdraw": "",
                "walletBalance": "55.0",
                "totalPositionIM": "0",
                "totalOrderIM": "0",
                "locked": "0",
                "bonus": "0",
                "usdValue": "55.0",
                "equity": "55.0",
            }
        ],
    }

    assert BybitClient._extract_available_balance_usd(wallet) == 55.0


def test_hyperliquid_uses_withdrawable_when_present() -> None:
    state = {
        "withdrawable": "29.78001",
        "marginSummary": {"accountValue": "29.78001", "totalMarginUsed": "0.0"},
        "crossMarginSummary": {"accountValue": "29.78001", "totalMarginUsed": "0.0"},
        "assetPositions": [],
    }

    assert HyperliquidClient._extract_available_balance_usd(state) == 29.78001


def test_hyperliquid_falls_back_to_account_value_minus_margin_used() -> None:
    state = {
        "withdrawable": "0",
        "marginSummary": {"accountValue": "80.0", "totalMarginUsed": "15.0"},
        "crossMarginSummary": {"accountValue": "75.0", "totalMarginUsed": "20.0"},
        "assetPositions": [],
    }

    assert HyperliquidClient._extract_available_balance_usd(state) == 65.0


def test_hyperliquid_resolves_agent_wallet_to_user_address() -> None:
    client = HyperliquidClient(
        private_key="0x" + ("11" * 32),
        is_testnet=True,
    )

    class FakeInfo:
        def user_role(self, address: str) -> dict[str, object]:
            assert address == client.wallet_address
            return {"role": "agent", "data": {"user": "0x1234567890abcdef1234567890abcdef12345678"}}

    async def fake_ensure_info_client():
        return FakeInfo()

    client._ensure_info_client = fake_ensure_info_client  # type: ignore[method-assign]

    resolved = asyncio.run(client.resolve_user_address())

    assert resolved == "0x1234567890abcdef1234567890abcdef12345678"
