from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from aiohttp import web

from bot.database.repository import (
    get_dashboard_health_data as repository_get_dashboard_health_data,
    get_daily_rejection_counts,
    get_open_positions as repository_get_open_positions,
    get_recent_execution_results as repository_get_recent_execution_results,
    get_recent_opportunities as repository_get_recent_opportunities,
    get_recent_positions as repository_get_recent_positions,
    get_recent_system_events as repository_get_recent_system_events,
)


async def run_dashboard_server(
    database_path: str,
    host: str,
    port: int,
    refresh_seconds: int,
    logger: logging.Logger,
) -> web.AppRunner:
    app = web.Application()
    app["database_path"] = database_path
    app["refresh_seconds"] = refresh_seconds

    app.router.add_get("/", dashboard_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/opportunities", opportunities_handler)
    app.router.add_get("/api/positions", positions_handler)
    app.router.add_get("/api/events", events_handler)
    app.router.add_get("/api/executions", executions_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("Dashboard available at http://%s:%s", host, port)
    return runner


async def dashboard_handler(request: web.Request) -> web.Response:
    payload = await _build_dashboard_payload(request.app["database_path"])
    html_body = _render_dashboard_html(payload, request.app["refresh_seconds"])
    return web.Response(text=html_body, content_type="text/html")


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response(
        await asyncio.to_thread(get_dashboard_health_data, request.app["database_path"])
    )


async def opportunities_handler(request: web.Request) -> web.Response:
    return web.json_response(
        await asyncio.to_thread(get_recent_opportunities, request.app["database_path"], 100)
    )


async def positions_handler(request: web.Request) -> web.Response:
    return web.json_response(
        await asyncio.to_thread(get_open_positions, request.app["database_path"])
    )


async def events_handler(request: web.Request) -> web.Response:
    return web.json_response(
        await asyncio.to_thread(get_recent_events, request.app["database_path"], 100)
    )


async def executions_handler(request: web.Request) -> web.Response:
    return web.json_response(
        await asyncio.to_thread(repository_get_recent_execution_results, request.app["database_path"], 100)
    )


def get_recent_events(database_path: str, limit: int = 25) -> list[dict[str, Any]]:
    return [event.__dict__ for event in repository_get_recent_system_events(database_path, limit)]


def get_recent_opportunities(database_path: str, limit: int = 25) -> list[dict[str, Any]]:
    return [opportunity.__dict__ for opportunity in repository_get_recent_opportunities(database_path, limit)]


def get_open_positions(database_path: str) -> list[dict[str, Any]]:
    return [position.__dict__ for position in repository_get_open_positions(database_path)]


def get_dashboard_health_data(database_path: str) -> dict[str, Any]:
    return repository_get_dashboard_health_data(database_path).__dict__


async def _build_dashboard_payload(database_path: str) -> dict[str, Any]:
    return await asyncio.to_thread(_load_dashboard_payload, database_path)


def _load_dashboard_payload(database_path: str) -> dict[str, Any]:
    health = get_dashboard_health_data(database_path)
    opportunities = get_recent_opportunities(database_path, limit=25)
    positions = [position.__dict__ for position in repository_get_recent_positions(database_path, limit=25)]
    events = get_recent_events(database_path, limit=25)
    executions = repository_get_recent_execution_results(database_path, limit=25)
    rejection_counts = get_daily_rejection_counts(database_path)

    return {
        "health": health,
        "opportunities": opportunities,
        "positions": positions,
        "events": events,
        "executions": executions,
        "rejection_counts": rejection_counts,
    }


def _render_dashboard_html(payload: dict[str, Any], refresh_seconds: int) -> str:
    health = payload["health"]
    summary_cards = "".join(
        _render_summary_card(label, value)
        for label, value in [
            ("Bot State", health["bot_state"]),
            ("Bybit Status", health["bybit_status"]),
            ("Hyperliquid Status", health["hyperliquid_status"]),
            ("Paused", str(health["paused"])),
            ("Rejected Net Positive Today", payload["rejection_counts"].get("rejected_net_positive", 0)),
            ("Rejected Risk Today", payload["rejection_counts"].get("rejected_risk", 0)),
        ]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arbitrage Bot Dashboard</title>
  <style>
    :root {{
      --bg: #f6f5ef;
      --panel: #ffffff;
      --ink: #15202b;
      --muted: #687076;
      --accent: #0b6e4f;
      --line: #dde4dd;
      --shadow: 0 18px 54px rgba(21, 32, 43, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(11, 110, 79, 0.10), transparent 35%),
        linear-gradient(180deg, #fcfcf7 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    main {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 30px 18px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.4rem);
      letter-spacing: -0.05em;
    }}
    p {{
      color: var(--muted);
      margin: 0 0 24px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }}
    .card {{
      padding: 16px;
    }}
    .card-label {{
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .card-value {{
      font-size: 1.8rem;
      color: var(--accent);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }}
    .panel {{
      padding: 18px;
      overflow: hidden;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 1.05rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-family: "Courier New", monospace;
      font-size: 0.82rem;
    }}
    th, td {{
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Delta-Neutral Operations Surface</h1>
    <p>Health, opportunities, positions, and recent events for the Bybit and Hyperliquid arbitrage bot.</p>
    <section class="cards">{summary_cards}</section>
    <section class="grid">
      <div class="panel">
        <h2>Health</h2>
        {_render_health_table(payload["health"])}
      </div>
      <div class="panel">
        <h2>Recent Opportunities</h2>
        {_render_opportunities_table(payload["opportunities"])}
      </div>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Open / Recent Positions</h2>
        {_render_positions_table(payload["positions"])}
      </div>
      <div class="panel">
        <h2>Recent Trades / Events</h2>
        {_render_events_table(payload["events"], payload["executions"])}
      </div>
    </section>
  </main>
</body>
</html>"""


def _render_summary_card(label: str, value: Any) -> str:
    return (
        f'<article class="card"><span class="card-label">{html.escape(str(label))}</span>'
        f'<strong class="card-value">{html.escape(str(value))}</strong></article>'
    )


def _render_health_table(health: dict[str, Any]) -> str:
    rows = [
        ("Bot State", health.get("bot_state")),
        ("Bybit Status", health.get("bybit_status")),
        ("Hyperliquid Status", health.get("hyperliquid_status")),
        ("Bybit Latency (ms)", health.get("bybit_latency_ms")),
        ("Hyperliquid Latency (ms)", health.get("hyperliquid_latency_ms")),
        ("Paused", health.get("paused")),
        ("Last Updated", health.get("last_updated")),
    ]
    return _render_key_value_table(rows)


def _render_opportunities_table(opportunities: list[dict[str, Any]]) -> str:
    if not opportunities:
        return "<p>No opportunities recorded yet.</p>"
    rows = []
    for opportunity in opportunities:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(opportunity['timestamp']))}</td>"
            f"<td>{html.escape(str(opportunity['symbol']))}</td>"
            f"<td>{html.escape(str(opportunity['strategy_type']))}</td>"
            f"<td>{html.escape(str(opportunity['decision']))}</td>"
            f"<td>{opportunity['gross_expected_bp']:.2f}</td>"
            f"<td>{opportunity['expected_net_bp']:.2f}</td>"
            f"<td>{html.escape(str(opportunity['reject_reason'] or ''))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Timestamp</th><th>Symbol</th><th>Strategy</th><th>Decision</th><th>Gross BP</th><th>Net BP</th><th>Reason</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_positions_table(positions: list[dict[str, Any]]) -> str:
    if not positions:
        return "<p>No positions tracked yet.</p>"
    rows = []
    for position in positions:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(position['entry_time']))}</td>"
            f"<td>{html.escape(str(position['symbol']))}</td>"
            f"<td>{html.escape(str(position['status']))}</td>"
            f"<td>{position['notional_usd']:.2f}</td>"
            f"<td>{position['current_pnl']:.2f}</td>"
            f"<td>{position['delta_imbalance_bp']:.2f}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Entry</th><th>Symbol</th><th>Status</th><th>Notional</th><th>PNL</th><th>Delta BP</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_events_table(
    events: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> str:
    rows = []
    for event in events[:10]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(event['timestamp']))}</td>"
            f"<td>event</td>"
            f"<td>{html.escape(str(event['event_type']))}</td>"
            f"<td>{html.escape(str(event['message']))}</td>"
            "</tr>"
        )
    for execution in executions[:10]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(execution['created_at']))}</td>"
            f"<td>trade</td>"
            f"<td>{html.escape(str(execution['status']))}</td>"
            f"<td>{html.escape(str(execution['reason']))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>No events recorded yet.</p>"
    return (
        "<table><thead><tr>"
        "<th>Timestamp</th><th>Type</th><th>Status</th><th>Message</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_key_value_table(rows: list[tuple[str, Any]]) -> str:
    rendered_rows = []
    for label, value in rows:
        rendered_rows.append(
            "<tr>"
            f"<th>{html.escape(str(label))}</th>"
            f"<td>{html.escape(str(value))}</td>"
            "</tr>"
        )
    return "<table><tbody>" + "".join(rendered_rows) + "</tbody></table>"
