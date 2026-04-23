from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

Environment = Literal["testnet", "live"]

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = BASE_DIR / ".env"

_CONFIG_CACHE: "Config | None" = None
_CONFIG_CACHE_MTIME: float | None = None


@dataclass(frozen=True)
class Config:
    environment: Environment
    bybit_api_key: str
    bybit_api_secret: str
    hyperliquid_private_key: str
    bybit_account_type: str
    bybit_settle_coin: str
    bybit_recv_window_ms: int
    hyperliquid_vault_address: str | None
    hyperliquid_account_address: str | None
    bybit_equity_override_usd: float | None
    bybit_available_balance_override_usd: float | None
    bybit_margin_used_override_usd: float | None
    hyperliquid_equity_override_usd: float | None
    hyperliquid_available_balance_override_usd: float | None
    hyperliquid_margin_used_override_usd: float | None
    bybit_rest_url: str
    hyperliquid_rest_url: str
    symbols: list[str]
    bybit_maker_fee_bp: float
    hyperliquid_maker_fee_bp: float
    slippage_buffer_bp: float
    safety_margin_bp: float
    min_net_expected_return_bp: float
    funding_diff_threshold_bp: float
    spread_threshold_bp: float
    expected_convergence_pct: float
    max_hold_minutes: int
    max_position_notional_usd: float
    margin_utilization_cap: float
    latency_pause_threshold_ms: float
    volatility_pause_threshold_pct: float
    reconciliation_interval_seconds: int
    poll_interval_seconds: int
    dashboard_host: str
    dashboard_port: int
    db_path: str
    log_path: str
    log_level: str
    near_miss_threshold_ratio: float
    liquidity_depth_fraction_limit: float
    min_margin_ratio_pct: float
    max_funding_prediction_horizon_hours: int
    execution_order_timeout_seconds: int
    execution_status_poll_interval_seconds: float
    pause_on_zero_effective_capital: bool
    allow_degraded_mode: bool
    dashboard_enabled: bool
    dashboard_refresh_seconds: int
    run_once: bool
    alert_webhook_url: str | None = None
    config_path: str = field(default=str(DEFAULT_CONFIG_PATH), repr=False)
    config_mtime: float | None = field(default=None, repr=False, compare=False)

    @property
    def is_testnet(self) -> bool:
        return self.environment == "testnet"

    @property
    def database_path(self) -> str:
        return self.db_path

    @property
    def log_file_path(self) -> str:
        return self.log_path

    @property
    def max_margin_utilization(self) -> float:
        return self.margin_utilization_cap

    @property
    def latency_guard_ms(self) -> float:
        return self.latency_pause_threshold_ms

    @property
    def volatility_spike_pct_1m(self) -> float:
        return self.volatility_pause_threshold_pct

    @property
    def min_gross_8h_funding_diff_bp(self) -> float:
        return self.funding_diff_threshold_bp

    @property
    def min_gross_entry_spread_bp(self) -> float:
        return self.spread_threshold_bp

    @property
    def max_hold_time_minutes(self) -> int:
        return self.max_hold_minutes


Settings = Config


def _resolve_config_path(path: str | Path | None = None) -> Path:
    if path is None:
        return DEFAULT_CONFIG_PATH
    return Path(path).expanduser().resolve()


def _load_env_file(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}
    loaded_values = dotenv_values(config_path)
    return {key: value for key, value in loaded_values.items() if value is not None}


def _read_value(
    name: str,
    default: str | None,
    file_values: dict[str, str],
    required: bool = False,
) -> str:
    value = os.getenv(name, file_values.get(name, "")).strip()
    if value:
        return value
    if required:
        raise ValueError(f"Missing required environment variable: {name}")
    if default is None:
        return ""
    return default


def _read_bool(name: str, default: bool, file_values: dict[str, str]) -> bool:
    raw_value = _read_value(name, str(default).lower(), file_values)
    return raw_value.lower() in {"1", "true", "yes", "y", "on"}


def _read_int(name: str, default: int, file_values: dict[str, str]) -> int:
    return int(_read_value(name, str(default), file_values))


def _read_float(name: str, default: float, file_values: dict[str, str]) -> float:
    return float(_read_value(name, str(default), file_values))


def _read_optional_float(name: str, file_values: dict[str, str]) -> float | None:
    raw_value = os.getenv(name, file_values.get(name, "")).strip()
    if not raw_value:
        return None
    return float(raw_value)


def load_config(
    path: str | Path | None = None,
    *,
    force_reload: bool = True,
) -> Config:
    global _CONFIG_CACHE, _CONFIG_CACHE_MTIME

    config_path = _resolve_config_path(path)
    config_mtime = config_path.stat().st_mtime if config_path.exists() else None
    if (
        not force_reload
        and _CONFIG_CACHE is not None
        and _CONFIG_CACHE_MTIME == config_mtime
        and Path(_CONFIG_CACHE.config_path) == config_path
    ):
        return _CONFIG_CACHE

    file_values = _load_env_file(config_path)
    environment = _read_value("ENVIRONMENT", "testnet", file_values)
    if environment not in {"testnet", "live"}:
        raise ValueError("ENVIRONMENT must be 'testnet' or 'live'")

    is_testnet = environment == "testnet"
    symbols_raw = _read_value("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT", file_values)
    symbols = [symbol.strip().upper() for symbol in symbols_raw.split(",") if symbol.strip()]

    config = Config(
        environment=environment,  # type: ignore[arg-type]
        bybit_api_key=_read_value("BYBIT_API_KEY", None, file_values, required=True),
        bybit_api_secret=_read_value("BYBIT_API_SECRET", None, file_values, required=True),
        hyperliquid_private_key=_read_value("HYPERLIQUID_PRIVATE_KEY", None, file_values, required=True),
        bybit_account_type=_read_value("BYBIT_ACCOUNT_TYPE", "UNIFIED", file_values).upper(),
        bybit_settle_coin=_read_value("BYBIT_SETTLE_COIN", "USDT", file_values).upper(),
        bybit_recv_window_ms=_read_int("BYBIT_RECV_WINDOW_MS", 5_000, file_values),
        hyperliquid_vault_address=_read_value("HYPERLIQUID_VAULT_ADDRESS", "", file_values) or None,
        hyperliquid_account_address=_read_value("HYPERLIQUID_ACCOUNT_ADDRESS", "", file_values) or None,
        bybit_equity_override_usd=_read_optional_float("BYBIT_EQUITY_OVERRIDE_USD", file_values),
        bybit_available_balance_override_usd=_read_optional_float(
            "BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD",
            file_values,
        ),
        bybit_margin_used_override_usd=_read_optional_float(
            "BYBIT_MARGIN_USED_OVERRIDE_USD",
            file_values,
        ),
        hyperliquid_equity_override_usd=_read_optional_float(
            "HYPERLIQUID_EQUITY_OVERRIDE_USD",
            file_values,
        ),
        hyperliquid_available_balance_override_usd=_read_optional_float(
            "HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD",
            file_values,
        ),
        hyperliquid_margin_used_override_usd=_read_optional_float(
            "HYPERLIQUID_MARGIN_USED_OVERRIDE_USD",
            file_values,
        ),
        bybit_rest_url=_read_value(
            "BYBIT_REST_URL",
            "https://api-testnet.bybit.com" if is_testnet else "https://api.bybit.com",
            file_values,
        ),
        hyperliquid_rest_url=_read_value(
            "HYPERLIQUID_REST_URL",
            "https://api.hyperliquid-testnet.xyz" if is_testnet else "https://api.hyperliquid.xyz",
            file_values,
        ),
        symbols=symbols,
        bybit_maker_fee_bp=_read_float("BYBIT_MAKER_FEE_BP", 2.0, file_values),
        hyperliquid_maker_fee_bp=_read_float("HYPERLIQUID_MAKER_FEE_BP", 1.5, file_values),
        slippage_buffer_bp=_read_float("SLIPPAGE_BUFFER_BP", 4.0, file_values),
        safety_margin_bp=_read_float("SAFETY_MARGIN_BP", 5.0, file_values),
        min_net_expected_return_bp=_read_float("MIN_NET_EXPECTED_RETURN_BP", 0.1, file_values),
        funding_diff_threshold_bp=_read_float("MIN_GROSS_8H_FUNDING_DIFF_BP", 16.0, file_values),
        spread_threshold_bp=_read_float("MIN_GROSS_ENTRY_SPREAD_BP", 16.0, file_values),
        expected_convergence_pct=_read_float("EXPECTED_CONVERGENCE_PCT", 85.0, file_values),
        max_hold_minutes=_read_int("MAX_HOLD_TIME_MINUTES", 5, file_values),
        max_position_notional_usd=_read_float("MAX_POSITION_NOTIONAL_USD", 10_000.0, file_values),
        margin_utilization_cap=_read_float("MAX_MARGIN_UTILIZATION", 0.30, file_values),
        latency_pause_threshold_ms=_read_float("LATENCY_GUARD_MS", 500.0, file_values),
        volatility_pause_threshold_pct=_read_float("VOLATILITY_SPIKE_PCT_1M", 2.0, file_values),
        reconciliation_interval_seconds=_read_int("RECONCILIATION_INTERVAL_SECONDS", 30, file_values),
        poll_interval_seconds=_read_int("POLL_INTERVAL_SECONDS", 5, file_values),
        dashboard_host=_read_value("DASHBOARD_HOST", "0.0.0.0", file_values),
        dashboard_port=_read_int("DASHBOARD_PORT", 8080, file_values),
        db_path=_read_value("DATABASE_PATH", "./arbitrage_bot.db", file_values),
        log_path=_read_value("LOG_FILE_PATH", "./logs/arbitrage_bot.log", file_values),
        log_level=_read_value("LOG_LEVEL", "INFO", file_values).upper(),
        near_miss_threshold_ratio=_read_float("NEAR_MISS_THRESHOLD_RATIO", 0.80, file_values),
        liquidity_depth_fraction_limit=_read_float("LIQUIDITY_DEPTH_FRACTION_LIMIT", 0.005, file_values),
        min_margin_ratio_pct=_read_float("MIN_MARGIN_RATIO_PCT", 150.0, file_values),
        max_funding_prediction_horizon_hours=_read_int(
            "MAX_FUNDING_PREDICTION_HORIZON_HOURS",
            8,
            file_values,
        ),
        execution_order_timeout_seconds=_read_int(
            "EXECUTION_ORDER_TIMEOUT_SECONDS",
            6,
            file_values,
        ),
        execution_status_poll_interval_seconds=_read_float(
            "EXECUTION_STATUS_POLL_INTERVAL_SECONDS",
            1.0,
            file_values,
        ),
        pause_on_zero_effective_capital=_read_bool(
            "PAUSE_ON_ZERO_EFFECTIVE_CAPITAL",
            True,
            file_values,
        ),
        allow_degraded_mode=_read_bool("ALLOW_DEGRADED_MODE", False, file_values),
        dashboard_enabled=_read_bool("DASHBOARD_ENABLED", True, file_values),
        dashboard_refresh_seconds=_read_int("DASHBOARD_REFRESH_SECONDS", 5, file_values),
        run_once=_read_bool("RUN_ONCE", False, file_values),
        alert_webhook_url=_read_value("ALERT_WEBHOOK_URL", "", file_values) or None,
        config_path=str(config_path),
        config_mtime=config_mtime,
    )

    _CONFIG_CACHE = config
    _CONFIG_CACHE_MTIME = config_mtime
    return config


def reload_config_if_needed(path: str | Path | None = None) -> Config:
    return load_config(path, force_reload=False)


def load_settings() -> Settings:
    return load_config()
