from __future__ import annotations

from bot.data_ingestion.bybit_client import BybitClient
from bot.data_ingestion.hyperliquid_client import HyperliquidClient
from bot.config.config import Config, load_config
from bot.execution.models import ExecutionIntent, ExecutionResult
from bot.execution.pair_executor import execute_delta_neutral_pair
from bot.signal_generator.models import TradeIntent


async def submit_execution_intent(
    intent: TradeIntent | ExecutionIntent,
    config: Config | None = None,
    bybit_client: BybitClient | None = None,
    hyperliquid_client: HyperliquidClient | None = None,
) -> ExecutionResult:
    runtime_config = config or load_config()
    trade_intent = intent if isinstance(intent, TradeIntent) else intent.to_trade_intent()
    return await execute_delta_neutral_pair(
        trade_intent,
        runtime_config,
        bybit_client=bybit_client,
        hyperliquid_client=hyperliquid_client,
    )
