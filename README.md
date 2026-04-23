# Delta-Neutral Arbitrage Bot MVP

Async Python MVP for delta-neutral perpetual futures arbitrage between Bybit and Hyperliquid. The bot now has a centralized config layer, a mandatory net-positive trade gate, opportunity and near-miss persistence, live private account integrations, maker-first paired execution, live reconciliation hooks, and a lightweight dashboard.

## Current Project Status

- Phase: Phase 2 implementation in progress
- Working today:
  - centralized runtime config in [bot/config/config.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/config/config.py)
  - funding and spread opportunity evaluation
  - mandatory net-positive gate in [bot/risk_engine/net_positive.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/risk_engine/net_positive.py)
  - structured pre-trade risk checks in [bot/risk_engine/checks.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/risk_engine/checks.py)
  - SQLite schema/repository for opportunities, positions, executions, and system events
  - dashboard and alert/logging surface
  - live private account state on Bybit and Hyperliquid
  - live maker-fee fetches for the net-positive gate
  - maker-first paired order routing with cancel/unwind handling
  - live position reconciliation loop
- Not complete yet:
  - websocket ingestion
  - backtesting, paper trading, and live deployment reporting
  - production-grade alert delivery
  - full fill-stream/websocket execution confirmation

## Repository Layout

```text
bot/
  config/
  data_ingestion/
  database/
  execution/
  monitoring/
  position_manager/
  risk_engine/
  signal_generator/
  main.py
scripts/
tests/
  unit/
```

## Quick Start

1. Copy `.env.example` to `.env` and populate credentials.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Run tests.
5. Start the bot.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
python -m bot.main
```

The dashboard will be available at `http://localhost:8080` by default.

On startup, the bot now runs a capital preflight before entering the scan loop. If usable paired capital cannot be resolved, startup exits with a clear error explaining exactly which inputs are missing, including likely fixes such as:

- funding the Bybit `UNIFIED` account behind the configured API key
- setting `HYPERLIQUID_ACCOUNT_ADDRESS` or `HYPERLIQUID_VAULT_ADDRESS`
- setting `BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD`
- setting `HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD`

## Config Parameters

The single source of truth is [bot/config/config.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/config/config.py). Use `load_config()` for initial load and `reload_config_if_needed()` for lightweight hot reload.

Core runtime parameters:

- Exchange environment settings:
  - `ENVIRONMENT`
  - `BYBIT_REST_URL`
  - `HYPERLIQUID_REST_URL`
  - `BYBIT_ACCOUNT_TYPE`
  - `BYBIT_SETTLE_COIN`
  - `BYBIT_RECV_WINDOW_MS`
  - `BYBIT_EQUITY_OVERRIDE_USD`
  - `BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD`
  - `BYBIT_MARGIN_USED_OVERRIDE_USD`
  - `HYPERLIQUID_VAULT_ADDRESS`
  - `HYPERLIQUID_ACCOUNT_ADDRESS`
  - `HYPERLIQUID_EQUITY_OVERRIDE_USD`
  - `HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD`
  - `HYPERLIQUID_MARGIN_USED_OVERRIDE_USD`
- Symbols:
  - `SYMBOLS`
- Fees and return controls:
  - `BYBIT_MAKER_FEE_BP`
  - `HYPERLIQUID_MAKER_FEE_BP`
  - `SLIPPAGE_BUFFER_BP`
  - `SAFETY_MARGIN_BP`
  - `MIN_NET_EXPECTED_RETURN_BP`
- Strategy thresholds:
  - `MIN_GROSS_8H_FUNDING_DIFF_BP`
  - `MIN_GROSS_ENTRY_SPREAD_BP`
  - `EXPECTED_CONVERGENCE_PCT`
  - `MAX_HOLD_TIME_MINUTES`
- Risk controls:
  - `MAX_POSITION_NOTIONAL_USD`
  - `MAX_MARGIN_UTILIZATION`
  - `LATENCY_GUARD_MS`
  - `VOLATILITY_SPIKE_PCT_1M`
  - `LIQUIDITY_DEPTH_FRACTION_LIMIT`
  - `MIN_MARGIN_RATIO_PCT`
  - `RECONCILIATION_INTERVAL_SECONDS`
  - `EXECUTION_ORDER_TIMEOUT_SECONDS`
  - `EXECUTION_STATUS_POLL_INTERVAL_SECONDS`
  - `PAUSE_ON_ZERO_EFFECTIVE_CAPITAL`
- Dashboard and storage:
  - `DASHBOARD_HOST`
  - `DASHBOARD_PORT`
  - `DATABASE_PATH`
  - `LOG_FILE_PATH`

## Mandatory Net-Positive Gate

The final trade gate lives in [bot/risk_engine/net_positive.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/risk_engine/net_positive.py).

Key functions:

- `get_current_bybit_maker_fee()`
- `get_current_hyperliquid_maker_fee()`
- `calculate_total_cost_bp()`
- `calculate_expected_net_bp()`
- `pre_trade_net_positive_check()`

The gate returns a structured `NetPositiveResult` with:

- `passed`
- `gross_expected_bp`
- `expected_net_bp`
- `total_cost_bp`
- `reject_reason`

No `TradeIntent` should be emitted unless this check passes.

## Opportunity and Near-Miss Logging

The bot persists scanner decisions in the SQLite database through [bot/database/repository.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/database/repository.py).

Primary tables:

- `opportunities`
- `position_pairs`
- `execution_results`
- `system_events`
- `market_snapshots`
- `funding_snapshots`

Opportunity decisions currently use:

- `accepted`
- `executed`
- `rejected_net_positive`
- `rejected_risk`
- `near_miss`

This supports later reporting for:

- trades rejected by the net-positive gate
- trades rejected by risk checks
- accepted opportunities that were deferred
- executed opportunities

## Dashboard Usage

The monitoring app is in [bot/monitoring/dashboard.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/monitoring/dashboard.py).

It exposes four operator views:

- Health:
  - bot state
  - exchange status
  - latest observed latency
  - paused/running state
- Opportunities:
  - accepted
  - rejected
  - near-misses
  - latest gross and net basis points
- Positions:
  - open or degraded pairs
  - current pnl
  - delta mismatch basis points
- Trades / Events:
  - recent executions
  - reconciliation events
  - health and pause events

Useful endpoints:

- `/`
- `/api/health`
- `/api/opportunities`
- `/api/positions`
- `/api/events`
- `/api/executions`

## Docker Run Commands

Build and run with Docker Compose:

```powershell
docker compose up --build -d
```

Stop the stack:

```powershell
docker compose down
```

The compose file uses restart policy `unless-stopped` and mounts:

- `./.env`
- `./logs`
- `./data`

## Testing

Run the full test suite:

```powershell
pytest
```

Additional unit coverage lives in:

- [tests/unit/test_net_positive.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/tests/unit/test_net_positive.py)
- [tests/unit/test_funding_strategy.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/tests/unit/test_funding_strategy.py)
- [tests/unit/test_risk_checks.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/tests/unit/test_risk_checks.py)

Integration note:

- Live Hyperliquid trading uses the official `hyperliquid-python-sdk`.
- Live Bybit trading uses signed V5 REST calls against the official endpoints.
- The current live execution path is maker-first and only records a pair as executed when both legs fill. If one leg fails or stalls, the bot cancels outstanding orders and attempts an unwind of the exposed side.
- Pair sizing now uses the smaller effective available balance across Bybit and Hyperliquid, not the summed balance, to stay delta-safe.
- If exchange snapshots are zero or unavailable, you can provide explicit per-exchange balance overrides through `.env` while keeping the raw snapshots logged for auditability.

## Phase 1 VPS Setup Checklist

1. Provision VPS and record the public IP.
2. Enforce SSH key-only auth and disable password login.
3. Enable UFW and allow only `22` and `443` if required.
4. Enable automatic security updates.
5. Install and enable `fail2ban`.
6. Install Docker and Docker Compose.
7. Clone the repository.
8. Populate `.env`.
9. Run the latency script:

```powershell
python scripts/latency_check.py
```

10. Record average round-trip latency to both testnet endpoints.
11. Start the bot with Docker Compose.
12. Confirm restart behavior and dashboard reachability.

## Known Limitations

- Execution is live-integrated but still polling-based in [bot/execution/pair_executor.py](/C:/Users/Jeremy%20Chan/arbitrage-bot/bot/execution/pair_executor.py), not websocket-confirmed yet.
- Hyperliquid fill attribution currently derives average fill price from recent fills filtered by `oid`, which is workable for MVP but should be hardened before larger deployment.
- Bybit order-state confirmation currently relies on REST polling rather than private websocket streams.
- Alerts are logging-first placeholders and are not yet wired to a real Telegram or Slack destination.
- No backtester, paper-trading engine, or live deployment reporting exists yet.
- If both effective exchange balances are zero and `PAUSE_ON_ZERO_EFFECTIVE_CAPITAL=true`, the bot will pause scanning instead of repeatedly emitting `$0.00` trade attempts.
