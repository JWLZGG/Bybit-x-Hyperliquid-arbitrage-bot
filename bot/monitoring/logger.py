from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from bot.database.models import SystemEvent
from bot.execution.models import ExecutionResult
from bot.signal_generator.models import Opportunity, TradeIntent


def configure_logger(
    log_level: str = "INFO",
    log_file_path: str | None = None,
) -> logging.Logger:
    logger = logging.getLogger("arbitrage_bot")
    logger.setLevel(log_level.upper())

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level.upper())

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if log_file_path:
        file_path = Path(log_file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(log_level.upper())
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def log_opportunity(logger: logging.Logger, opportunity: Opportunity) -> None:
    logger.info(
        (
            "Opportunity %s %s | decision=%s | gross=%0.2f bp | "
            "net=%0.2f bp | cost=%0.2f bp | reject_reason=%s"
        ),
        opportunity.symbol,
        opportunity.strategy_type,
        opportunity.decision,
        opportunity.gross_expected_bp,
        opportunity.expected_net_bp,
        opportunity.total_cost_bp,
        opportunity.reject_reason or "none",
    )


def log_trade_intent(logger: logging.Logger, intent: TradeIntent) -> None:
    logger.info(
        (
            "Trade intent %s %s | bybit_side=%s | hyperliquid_side=%s | "
            "notional=%0.2f | gross=%0.2f bp | net=%0.2f bp"
        ),
        intent.symbol,
        intent.strategy_type,
        intent.bybit_side,
        intent.hyperliquid_side,
        intent.target_notional_usd,
        intent.gross_expected_bp,
        intent.expected_net_bp,
    )


def log_rejection(logger: logging.Logger, opportunity: Opportunity, reason: str) -> None:
    logger.warning(
        "Rejected %s %s | decision=%s | reason=%s",
        opportunity.symbol,
        opportunity.strategy_type,
        opportunity.decision,
        reason,
    )


def log_execution_result(logger: logging.Logger, result: ExecutionResult) -> None:
    logger.info(
        (
            "Execution result %s %s | status=%s | accepted=%s | "
            "bybit_leg=%s | hyperliquid_leg=%s | reason=%s"
        ),
        result.symbol,
        result.strategy_type,
        result.status,
        result.accepted,
        result.bybit_leg.status,
        result.hyperliquid_leg.status,
        result.reason,
    )


def log_reconciliation_event(logger: logging.Logger, event: SystemEvent) -> None:
    logger.warning(
        "Reconciliation event %s | level=%s | message=%s",
        event.event_type,
        event.level,
        event.message,
    )


def log_system_health(
    logger: logging.Logger,
    *,
    bot_state: str,
    bybit_ok: bool,
    hyperliquid_ok: bool,
    bybit_latency_ms: float | None = None,
    hyperliquid_latency_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    logger.info(
        (
            "System health | bot_state=%s | bybit_ok=%s | hyperliquid_ok=%s | "
            "bybit_latency_ms=%s | hyperliquid_latency_ms=%s | extra=%s"
        ),
        bot_state,
        bybit_ok,
        hyperliquid_ok,
        bybit_latency_ms,
        hyperliquid_latency_ms,
        extra or {},
    )
