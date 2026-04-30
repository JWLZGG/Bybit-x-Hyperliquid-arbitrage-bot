# Delta-Neutral Arbitrage Bot MVP

Async Python MVP for delta-neutral perpetual futures arbitrage between **Bybit** and **Hyperliquid**.

The bot continuously scans supported symbols, evaluates **funding arbitrage** and **price-spread convergence** opportunities, applies a **mandatory net-positive gate** plus pre-trade risk checks and routes opportunities into either **paper execution** or guarded live execution paths.

This MVP is designed to answer two questions safely:

1. **Is there a tradable cross-venue edge after realistic costs?**
2. **If not, can the system correctly suppress uneconomic live deployment?**

---

## Final MVP Status

### Completed
- centralized runtime config in `bot/config/config.py`
- Bybit and Hyperliquid market-data ingestion
- live private account-state integration
- live maker-fee fetches for cost modeling
- funding-arbitrage and spread-convergence opportunity evaluation
- mandatory net-positive gate in `bot/risk_engine/net_positive.py`
- structured pre-trade risk checks in `bot/risk_engine/checks.py`
- SQLite persistence for:
  - opportunities
  - position pairs
  - execution results
  - system events
  - market snapshots
  - funding snapshots
  - paper trades
  - cycle summaries
  - best-opportunity snapshots
- paper execution path with duplicate suppression
- reconciliation loop and realized PnL tracking
- cycle-level summaries and best-opportunity reporting
- Phase 4 snapshot reporting
- dashboard and logging / alert surface
- maker-first paired live execution routing with cancel / unwind handling

### Key final finding
The MVP is technically operational and report-complete, but under tested **major-pair conditions** on **BTCUSDT, ETHUSDT and SOLUSDT** between Bybit and Hyperliquid, observed gross edge did **not** overcome realistic modeled execution costs.

That is an important successful outcome for a guarded trading system: the bot correctly identified near-miss opportunities and **suppressed uneconomic live execution**.

### What this means
This repository should be understood as a **working arbitrage research and execution framework** with paper-trading validation and live-deployment guardrails, rather than a claim of immediate production profitability under the tested market regime.

---

## Repository Layout

```text
bot/
  analytics/
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
1. Copy environment template
```bash
cp .env.example .env
```

Populate credentials and runtime values in .env.

2. Create and activate a virtual environment

Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```
3. Install dependencies
```bash
pip install -r requirements.txt
```
4. Run tests
```bash
pytest
```
5. Start the bot
```bash
python -m bot.main
```
The dashboard is available at:
```text
http://localhost:8080
```
## Docker Usage

### Start in background

```bash
docker compose up --build -d
```

### Follow logs

```bash
docker compose logs --tail=200 -f
```

###Stop
=======

### Stop

```bash
docker compose down
```

The compose setup mounts:

- `./.env`
- `./logs`
- `./data`

and uses restart policy `unless-stopped`.

## Runtime Modes

### Paper / simulated mode

Recommended default for evaluation and reporting.

Typical settings:

- `LIVE_EXECUTION_ENABLED=false`
- optional exchange balance overrides for simulation
- paper execution and reconciliation enabled

### Live mode

Enable only when:

- both exchanges are correctly funded
- credentials are verified
- expected net edge is positive in current market conditions
- notional limits are reduced for a canary deployment
- reporting confirms live opportunities are clearing cost assumptions

## Startup Capital Preflight

On startup, the bot performs a capital preflight before entering the scan loop.

If usable paired capital cannot be resolved, startup exits or pauses with a clear explanation of what is missing, including likely fixes such as:

- funding the Bybit UNIFIED account behind the configured API key
- setting `HYPERLIQUID_ACCOUNT_ADDRESS` or `HYPERLIQUID_VAULT_ADDRESS`
- setting `BYBIT_AVAILABLE_BALANCE_OVERRIDE_USD`
- setting `HYPERLIQUID_AVAILABLE_BALANCE_OVERRIDE_USD`

This behaviour is intentional and helps prevent invalid $0 trade attempts.

## Configuration

The single source of truth is:

```text
bot/config/config.py
```

Use:

- `load_config()` for initial load
- `reload_config_if_needed()` for lightweight hot reload

## Core runtime parameters

### Exchange environment
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

### Symbols
- `SYMBOLS`
### Fees and return controls
- `BYBIT_MAKER_FEE_BP`
- `HYPERLIQUID_MAKER_FEE_BP`
- `SLIPPAGE_BUFFER_BP`
- `SAFETY_MARGIN_BP`
- `MIN_NET_EXPECTED_RETURN_BP`
### Strategy thresholds
- `MIN_GROSS_8H_FUNDING_DIFF_BP`
- `MIN_GROSS_ENTRY_SPREAD_BP`
- `EXPECTED_CONVERGENCE_PCT`
- `MAX_HOLD_TIME_MINUTES`
### Risk controls
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
### Dashboard and storage
- `DASHBOARD_HOST`
- `DASHBOARD_PORT`
- `DATABASE_PATH`
- `LOG_FILE_PATH`

## Mandatory Net-Positive Gate

The final trade gate lives in:

```text
bot/risk_engine/net_positive.py
```

Key functions include:

- `get_current_bybit_maker_fee()`
- `get_current_hyperliquid_maker_fee()`
- `calculate_total_cost_bp()`
- `calculate_expected_net_bp()`
- `pre_trade_net_positive_check()`

The gate returns a structured NetPositiveResult containing:

- `passed`
- `gross_expected_bp`
- `expected_net_bp`
- `total_cost_bp`
- `reject_reason`

No `TradeIntent` should be emitted unless this check passes.

This is one of the most important safety features in the MVP.

## Opportunity Classification

The bot persists scanner decisions and execution outcomes into SQLite.

Primary decision states include:

- `accepted`
- `executed`
- `rejected_net_positive`
- `rejected_risk`
- `near_miss`

This supports later reporting on:

- trades rejected by the net-positive gate
- trades rejected by risk checks
- accepted opportunities that were deferred
- executed opportunities
- near-miss opportunities worth further study

## Paper Trading and Reporting

The MVP now includes:

- paper trade creation and duplicate suppression
- reconciliation of open paper trades
- realised PnL tracking
- win rate and average holding time summaries
- cycle-level reporting:
  - scanned count
  - accepted count
  - near-miss count
  - rejected count
  - open paper trade count
- best-opportunity snapshots
- Phase 4 summary snapshots over time

This makes the system suitable for:

- controlled strategy observation
- edge validation
- internal reporting to CRA / Horizon One
- deciding whether live deployment is justified

## Dashboard Usage

The monitoring app lives in:

```text
bot/monitoring/dashboard.py
```

It exposes operator views for:

### Health
- bot state
- exchange status
- observed latency
- paused / running state

### Opportunities
- accepted
- rejected
- near-misses
- latest gross and net basis points
### Positions
- open or degraded pairs
- current PnL
- delta mismatch basis points
### Trades / Events
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

## Testing

Run the full test suite with:
```bash
pytest
```
Current automated coverage should be described as targeted MVP coverage, not exhaustive production-hardening coverage.

The strongest current coverage areas are:

- net-positive gate behaviour
- funding strategy logic
- risk checks
- paper-trading and reporting paths

Representative unit tests include:

- `tests/unit/test_net_positive.py`
- `tests/unit/test_funding_strategy.py`
- `tests/unit/test_risk_checks.py`

### Coverage position

The codebase is now materially more testable than earlier in the build because strategy logic, execution flow, reconciliation, and reporting are more clearly separated. Additional integration and failure-path testing is recommended before any persistent live deployment.

## VPS Deployment Checklist

### Phase 1 infrastructure
- provision VPS and record public IP
- enforce SSH key-only auth
- disable password login
- enable UFW and restrict ports
- enable automatic security updates
- install and enable fail2ban
- install Docker and Docker Compose
- clone the repository
- populate `.env`
- run latency checks:
```bash
python scripts/latency_check.py
```
- record average round-trip latency to both endpoints
- start the bot with Docker Compose
- confirm restart behavior and dashboard reachability

## Known Limitations
- Execution remains polling-based in bot/execution/pair_executor.py rather than websocket-confirmed.
- Hyperliquid fill attribution still derives average fill price from recent fills filtered by oid; workable for MVP, but should be hardened before larger live deployment.
- Bybit order-state confirmation still relies on REST polling rather than private websocket streams.
- Alerts are logging-first placeholders and are not yet wired to Telegram / Slack.
- Current major-pair testing did not demonstrate repeated positive net edge after realistic costs.
- Live deployment should therefore be treated as gated, not assumed.

## Recommendations / Next Steps
1. Focus strategy work on the branch closest to viability in current observations.
2. Expand beyond the initial major-pair universe.
3. Improve execution quality and effective fee tier.
4. Use the first live deployment only as a tightly controlled canary.
5. Extend automated testing around integration failure modes and execution edge cases.

## Bottom Line

This MVP successfully answers a critical desk-level question:

When does apparent cross-venue arbitrage survive realistic costs — and when should the system refuse to trade?

In the tested market regime, the correct answer was often: do not trade yet.

That is not a failure of the system.
That is the system working as intended.
