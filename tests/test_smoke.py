from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from bot.config.settings import load_settings
from bot.database.db import initialize_database


def test_load_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "testnet")
    monkeypatch.setenv("BYBIT_API_KEY", "dummy_key")
    monkeypatch.setenv("BYBIT_API_SECRET", "dummy_secret")
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "dummy_private_key")
    monkeypatch.setenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
    monkeypatch.setenv("DATABASE_PATH", "./test_smoke.db")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "5")

    settings = load_settings()

    assert settings.environment == "testnet"
    assert settings.is_testnet is True
    assert settings.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert settings.database_path == "./test_smoke.db"
    assert settings.min_gross_8h_funding_diff_bp == 16.0
    assert settings.dashboard_enabled is True


def test_initialize_database_creates_expected_tables() -> None:
    db_path = Path.cwd() / f"test-smoke-{uuid4().hex}.db"

    try:
        initialize_database(str(db_path))

        connection = sqlite3.connect(db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )
            table_names = {row[0] for row in cursor.fetchall()}
        finally:
            connection.close()

        assert "heartbeat" in table_names
        assert "market_snapshots" in table_names
        assert "scanner_events" in table_names
    finally:
        if db_path.exists():
            db_path.unlink()
