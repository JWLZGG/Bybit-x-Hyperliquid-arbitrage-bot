import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import aiohttp

from bot.config.config import load_config
from bot.data_ingestion.hyperliquid_client import HyperliquidClient

async def post_info(base_url, body):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/info", json=body, timeout=10) as response:
            text = await response.text()
            print("\nREQUEST:", body)
            print("STATUS:", response.status)
            try:
                print(json.dumps(json.loads(text), indent=2, sort_keys=True))
            except Exception:
                print(text)

async def main():
    config = load_config()
    hyper = HyperliquidClient(
        private_key=config.hyperliquid_private_key,
        is_testnet=config.is_testnet,
        base_url=config.hyperliquid_rest_url,
        vault_address=config.hyperliquid_vault_address,
        account_address=config.hyperliquid_account_address,
    )

    configured = (config.hyperliquid_account_address or "").lower()
    signer = hyper.wallet_address.lower()
    resolved = (await hyper.resolve_user_address()).lower()

    print("base_url:", config.hyperliquid_rest_url)
    print("configured:", configured)
    print("signer:", signer)
    print("resolved:", resolved)

    addresses = []
    for address in [configured, signer, resolved]:
        if address and address not in addresses:
            addresses.append(address)

    for address in addresses:
        print("\n==============================")
        print("ADDRESS:", address)
        print("==============================")

        await post_info(config.hyperliquid_rest_url, {
            "type": "clearinghouseState",
            "user": address,
        })

        await post_info(config.hyperliquid_rest_url, {
            "type": "spotClearinghouseState",
	    "user": address,
        })

asyncio.run(main())

