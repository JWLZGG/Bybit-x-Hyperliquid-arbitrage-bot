import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json

from bot.config.config import load_config
from bot.data_ingestion.hyperliquid_client import HyperliquidClient

async def main():
    config = load_config()

    hyper = HyperliquidClient(
        private_key=config.hyperliquid_private_key,
        is_testnet=config.is_testnet,
        base_url=config.hyperliquid_rest_url,
        vault_address=config.hyperliquid_vault_address,
        account_address=config.hyperliquid_account_address,
    )

    info, _ = await hyper._ensure_sdk_clients()
    user_address = await hyper.resolve_user_address()

    print("configured account:", config.hyperliquid_account_address)
    print("signer wallet:", hyper.wallet_address)
    print("resolved user:", user_address)
    print("identity:", await hyper.resolve_user_identity())

    state = await asyncio.to_thread(info.user_state, user_address)

    print(json.dumps(state, indent=2, sort_keys=True))

asyncio.run(main())
