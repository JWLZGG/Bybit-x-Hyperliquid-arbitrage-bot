import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
from bot.config.config import load_config
from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient

async def main():
    config = load_config()

    bybit = BybitClient(
        api_key=config.bybit_api_key,
        api_secret=config.bybit_api_secret,
        is_testnet=config.is_testnet,
        base_url=config.bybit_rest_url,
        recv_window_ms=config.bybit_recv_window_ms,
        account_type=config.bybit_account_type,
        settle_coin=config.bybit_settle_coin,
    )

    hyper = HyperliquidClient(
        private_key=config.hyperliquid_private_key,
        is_testnet=config.is_testnet,
        base_url=config.hyperliquid_rest_url,
        vault_address=config.hyperliquid_vault_address,
        account_address=config.hyperliquid_account_address,
    )

    print("ENV:", config.environment)
    print("BYBIT account type:", config.bybit_account_type)
    print("BYBIT settle coin:", config.bybit_settle_coin)
    print("HL configured account:", config.hyperliquid_account_address)
    print("HL vault:", config.hyperliquid_vault_address)

    print("\n--- Bybit healthcheck ---")
    try:
        print(await bybit.healthcheck())
    except Exception as e:
        print("BYBIT healthcheck error:", repr(e))

    print("\n--- Bybit account snapshot ---")
    try:
        bybit_snapshot = await bybit.get_account_snapshot()
        print(bybit_snapshot)
    except Exception as e:
        print("BYBIT account snapshot error:", repr(e))

    print("\n--- Hyperliquid identity ---")
    try:
        print(await hyper.resolve_user_identity())
    except Exception as e:
        print("HL identity error:", repr(e))

    print("\n--- Hyperliquid account snapshot ---")
    try:
        hyper_snapshot = await hyper.get_account_snapshot()
        print(hyper_snapshot)
    except Exception as e:
        print("HL account snapshot error:", repr(e))

asyncio.run(main())
