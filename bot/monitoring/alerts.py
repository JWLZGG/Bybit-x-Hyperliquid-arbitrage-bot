from __future__ import annotations

import logging
from typing import Any

from bot.execution.models import PositionPair
from bot.signal_generator.models import Opportunity


def _emit_alert(
    logger: logging.Logger,
    alert_type: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    logger.warning("ALERT %s | %s | metadata=%s", alert_type, message, metadata or {})
    return {
        "alert_type": alert_type,
        "message": message,
        "metadata": metadata or {},
        "sent": False,
    }


def send_bot_started_alert(logger: logging.Logger) -> dict[str, Any]:
    return _emit_alert(logger, "bot_started", "Arbitrage bot started")


def send_trade_entered_alert(
    logger: logging.Logger,
    position_pair: PositionPair,
) -> dict[str, Any]:
    return _emit_alert(
        logger,
        "trade_entered",
        f"Entered {position_pair.symbol} {position_pair.strategy_type} pair",
        {"position_pair_id": position_pair.id, "status": position_pair.status},
    )


def send_trade_rejected_alert(
    logger: logging.Logger,
    opportunity: Opportunity,
) -> dict[str, Any]:
    return _emit_alert(
        logger,
        "trade_rejected",
        f"Rejected {opportunity.symbol} {opportunity.strategy_type}",
        {"decision": opportunity.decision, "reason": opportunity.reject_reason},
    )


def send_one_leg_risk_alert(
    logger: logging.Logger,
    symbol: str,
    reason: str,
) -> dict[str, Any]:
    return _emit_alert(logger, "one_leg_risk", f"{symbol} one-leg risk: {reason}")


def send_pause_trigger_alert(
    logger: logging.Logger,
    reason: str,
) -> dict[str, Any]:
    return _emit_alert(logger, "pause_trigger", f"Bot paused: {reason}")


def send_disconnect_alert(
    logger: logging.Logger,
    exchange: str,
) -> dict[str, Any]:
    return _emit_alert(logger, "disconnect", f"{exchange} disconnected")
