from __future__ import annotations

import os
import time
from dataclasses import replace
from typing import Any

_CANARY_TRADE_TIMESTAMPS: list[float] = []


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _symbol_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _get_expected_net_bp(intent: Any) -> float | None:
    """
    Support several possible field names because different internal models
    may call this value expected_net_bp, net_bp, or expected_net_return_bp.
    """
    for attr in (
        "expected_net_bp",
        "net_bp",
        "expected_net_return_bp",
        "expected_net_return",
    ):
        value = getattr(intent, attr, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _get_notional(intent: Any) -> float:
    value = getattr(intent, "target_notional_usd", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cap_notional(intent: Any, max_notional: float) -> Any:
    current = _get_notional(intent)
    if current <= max_notional:
        return intent

    try:
        return replace(intent, target_notional_usd=max_notional)
    except TypeError:
        # Fall back to mutating only if this is not a frozen dataclass.
        try:
            intent.target_notional_usd = max_notional
        except Exception:
            pass
        return intent


def _trades_in_last_hour() -> int:
    now = time.time()
    cutoff = now - 3600
    while _CANARY_TRADE_TIMESTAMPS and _CANARY_TRADE_TIMESTAMPS[0] < cutoff:
        _CANARY_TRADE_TIMESTAMPS.pop(0)
    return len(_CANARY_TRADE_TIMESTAMPS)


def validate_canary_intent(intent: Any) -> tuple[bool, str, Any]:
    live_enabled = _env_bool("LIVE_EXECUTION_ENABLED", False)
    canary_enabled = _env_bool("CANARY_EXECUTION_ENABLED", False)
    canary_dry_run = _env_bool("CANARY_DRY_RUN", True)

    if not live_enabled:
        return False, "LIVE_EXECUTION_ENABLED is false; refusing live execution", intent

    if not canary_enabled:
        return False, "CANARY_EXECUTION_ENABLED is false; refusing live canary execution", intent

    symbol = str(getattr(intent, "symbol", "")).upper()
    allowed_symbols = _symbol_set("CANARY_SYMBOLS")
    if allowed_symbols and symbol not in allowed_symbols:
        return False, f"Canary symbol {symbol} is not allowed; allowed={sorted(allowed_symbols)}", intent

    required_net_bp = _env_float("CANARY_REQUIRE_NET_BP", 10.0)
    expected_net_bp = _get_expected_net_bp(intent)
    if expected_net_bp is None:
        return False, "Intent has no expected_net_bp/net_bp field; refusing canary execution", intent

    if expected_net_bp < required_net_bp:
        return (
            False,
            f"Expected net bp {expected_net_bp:.4f} below canary requirement {required_net_bp:.4f}",
            intent,
        )

    max_notional = _env_float("CANARY_MAX_NOTIONAL_USD", 2.0)
    capped_intent = _cap_notional(intent, max_notional)

    max_trades_per_hour = _env_int("CANARY_MAX_TRADES_PER_HOUR", 1)
    if _trades_in_last_hour() >= max_trades_per_hour:
        return False, f"Canary max trades/hour reached: {max_trades_per_hour}", capped_intent

    if canary_dry_run:
        return False, "CANARY_DRY_RUN is true; refusing live canary execution", capped_intent

    return True, "Canary execution guard passed", capped_intent


def record_canary_trade(symbol: str | None = None) -> None:
    _CANARY_TRADE_TIMESTAMPS.append(time.time())
