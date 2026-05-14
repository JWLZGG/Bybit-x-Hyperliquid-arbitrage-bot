from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from bot.config.config import load_config
from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient


def bp(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 10_000


async def main() -> None:
    config = load_config()

    bybit = BybitClient(
        api_key=config.bybit_api_key,
        api_secret=config.bybit_api_secret,
        is_testnet=config.environment == "testnet",
        base_url=config.bybit_rest_url,
        recv_window_ms=config.bybit_recv_window_ms,
        account_type=config.bybit_account_type,
        settle_coin=config.bybit_settle_coin,
    )

    hyper = HyperliquidClient(
        private_key=config.hyperliquid_private_key,
        is_testnet=config.environment == "testnet",
        base_url=config.hyperliquid_rest_url,
        account_address=config.hyperliquid_account_address,
        vault_address=config.hyperliquid_vault_address,
    )

    total_cost_bp = (
        config.bybit_maker_fee_bp * 2
        + config.hyperliquid_maker_fee_bp * 2
        + config.slippage_buffer_bp
        + config.safety_margin_bp
    )

    print("symbol,bybit_bid,bybit_ask,hl_bid,hl_ask,buy_bybit_sell_hl_bp,buy_hl_sell_bybit_bp,best_direction,best_gross_bp,est_net_bp,total_cost_bp")

    for symbol in config.symbols:
        try:
            bybit_quote, hyper_quote = await asyncio.gather(
                bybit.get_best_bid_ask(symbol),
                hyper.get_best_bid_ask(symbol),
            )

            buy_bybit_sell_hl = bp(
                hyper_quote.bid_price - bybit_quote.ask_price,
                bybit_quote.ask_price,
            )
            buy_hl_sell_bybit = bp(
                bybit_quote.bid_price - hyper_quote.ask_price,
                hyper_quote.ask_price,
            )

            if buy_bybit_sell_hl >= buy_hl_sell_bybit:
                direction = "buy_bybit_sell_hyperliquid"
                best_gross = buy_bybit_sell_hl
            else:
                direction = "buy_hyperliquid_sell_bybit"
                best_gross = buy_hl_sell_bybit

            est_net = best_gross - total_cost_bp

            print(
                f"{symbol},"
                f"{bybit_quote.bid_price},"
                f"{bybit_quote.ask_price},"
                f"{hyper_quote.bid_price},"
                f"{hyper_quote.ask_price},"
                f"{buy_bybit_sell_hl:.4f},"
                f"{buy_hl_sell_bybit:.4f},"
                f"{direction},"
                f"{best_gross:.4f},"
                f"{est_net:.4f},"
                f"{total_cost_bp:.4f}"
            )

        except Exception as exc:
            print(f"{symbol},ERROR,{type(exc).__name__},{exc}")


if __name__ == "__main__":
    asyncio.run(main())
