from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Tick:
    """
    Tick = a single live market update.

    symbol: which stock (e.g., TSLA)
    ts: when the tick happened (timestamp)
    price: traded price
    size: traded size (volume for this tick)
    """
    symbol: str
    ts: datetime
    price: float
    size: float


@dataclass
class Candle:
    """
    Candle (OHLCV) for a fixed timeframe window (we start with 1 minute).

    start_ts: the start time of the candle window (e.g., 10:05:00)
    end_ts: the end time boundary (e.g., 10:06:00) - not inclusive
    o/h/l/c: open/high/low/close prices during the window
    v: summed volume during the window
    """
    symbol: str
    timeframe: str  # "1m" for now
    start_ts: datetime
    end_ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: float

    def update(self, price: float, size: float) -> None:
        """Update this candle with a new tick."""
        self.h = max(self.h, price)
        self.l = min(self.l, price)
        self.c = price
        self.v += size
