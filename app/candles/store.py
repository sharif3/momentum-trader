from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from app.models.market import Candle


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CandleStore:
    """
    In-memory candle storage + freshness tracking.

    current[(symbol, timeframe)]  -> candle being built
    history[(symbol, timeframe)]  -> closed candles (latest N)
    last_updated[(symbol, timeframe)] -> when we last touched data for that TF
      - for 1m: updated on each tick (because candle is being updated)
      - for 5m: updated when we update the current 5m from a closed 1m candle
      - for higher TF (later): updated when REST refresh writes candles
    """
    max_history: int = 500
    current: Dict[Tuple[str, str], Candle] = field(default_factory=dict)
    history: Dict[Tuple[str, str], List[Candle]] = field(default_factory=dict)
    last_updated: Dict[Tuple[str, str], datetime] = field(default_factory=dict)

    def touch(self, symbol: str, timeframe: str) -> None:
        """Mark this symbol/timeframe as updated right now."""
        self.last_updated[(symbol, timeframe)] = utcnow()

    def get_current(self, symbol: str, timeframe: str) -> Optional[Candle]:
        return self.current.get((symbol, timeframe))

    def set_current(self, candle: Candle) -> None:
        self.current[(candle.symbol, candle.timeframe)] = candle
        self.touch(candle.symbol, candle.timeframe)

    def close_current(self, symbol: str, timeframe: str) -> Optional[Candle]:
        key = (symbol, timeframe)
        candle = self.current.pop(key, None)
        if candle is None:
            return None

        hist = self.history.setdefault(key, [])
        hist.append(candle)

        if len(hist) > self.max_history:
            del hist[:-self.max_history]

        self.touch(symbol, timeframe)
        return candle

    def get_history(self, symbol: str, timeframe: str) -> List[Candle]:
        return self.history.get((symbol, timeframe), [])

    def get_last_updated(self, symbol: str, timeframe: str) -> Optional[datetime]:
        return self.last_updated.get((symbol, timeframe))

    def has_any_data(self, symbol: str, timeframe: str) -> bool:
        """True if we have either a current candle or any closed candles."""
        key = (symbol, timeframe)
        return key in self.current or len(self.history.get(key, [])) > 0

    def is_fresh(self, symbol: str, timeframe: str, max_age_seconds: int) -> bool:
        """
        Freshness check:
        - Must have some data
        - last_updated must be within max_age_seconds
        """
        if not self.has_any_data(symbol, timeframe):
            return False

        last = self.get_last_updated(symbol, timeframe)
        if last is None:
            return False

        return (utcnow() - last) <= timedelta(seconds=max_age_seconds)

    def replace_history(self, symbol: str, timeframe: str, candles: List[Candle]) -> None:
        """
        Replace stored closed candles for a timeframe in one shot.
        Used for REST refresh of higher timeframes.
        """
        key = (symbol, timeframe)
        self.history[key] = candles[-self.max_history:]
        # Remove any current forming candle for that TF (REST data is closed bars)
        self.current.pop(key, None)
        self.touch(symbol, timeframe)
    
