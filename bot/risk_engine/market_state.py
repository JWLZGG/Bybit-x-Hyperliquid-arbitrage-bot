from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class MarketStateTracker:
    def __init__(self, history_window_seconds: int = 60) -> None:
        self.history_window = timedelta(seconds=history_window_seconds)
        self._price_history: dict[tuple[str, str], deque[tuple[datetime, float]]] = defaultdict(deque)
        self._depth_history: dict[tuple[str, str], deque[tuple[datetime, float]]] = defaultdict(deque)
        self._latest_price: dict[tuple[str, str], float] = {}
        self._latest_depth: dict[tuple[str, str], float] = {}

    def record_price(
        self,
        exchange: str,
        symbol: str,
        mark_price: float,
        observed_at: datetime,
    ) -> None:
        self._append(self._price_history[(exchange, symbol)], observed_at, mark_price)
        self._latest_price[(exchange, symbol)] = mark_price

    def record_depth(
        self,
        exchange: str,
        symbol: str,
        depth_usd: float,
        observed_at: datetime,
    ) -> None:
        self._append(self._depth_history[(exchange, symbol)], observed_at, depth_usd)
        self._latest_depth[(exchange, symbol)] = depth_usd

    def one_minute_move_pct(self, exchange: str, symbol: str) -> float | None:
        history = self._price_history[(exchange, symbol)]
        if len(history) < 2:
            return None

        oldest_price = history[0][1]
        latest_price = history[-1][1]
        if oldest_price <= 0:
            return None

        return abs((latest_price - oldest_price) / oldest_price) * 100

    def average_depth_usd(self, exchange: str, symbol: str) -> float | None:
        history = self._depth_history[(exchange, symbol)]
        if not history:
            return None

        total_depth = sum(depth for _, depth in history)
        return total_depth / len(history)

    def latest_depth_usd(self, exchange: str, symbol: str) -> float | None:
        return self._latest_depth.get((exchange, symbol))

    def latest_price(self, exchange: str, symbol: str) -> float | None:
        return self._latest_price.get((exchange, symbol))

    def _append(
        self,
        series: deque[tuple[datetime, float]],
        observed_at: datetime,
        value: float,
    ) -> None:
        normalized_time = observed_at.astimezone(timezone.utc)
        series.append((normalized_time, value))
        self._prune(series, normalized_time)

    def _prune(
        self,
        series: deque[tuple[datetime, float]],
        now: datetime,
    ) -> None:
        cutoff = now - self.history_window
        while series and series[0][0] < cutoff:
            series.popleft()
