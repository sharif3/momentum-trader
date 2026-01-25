from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.models.market import Candle


@dataclass
class CandleStore:
    """
    In-memory candle storage.

    - current[(symbol, timeframe)] holds the candle being built right now
    - history[(symbol, timeframe)] holds closed candles (latest N)
    """
    max_history: int = 500
    current: Dict[Tuple[str, str], Candle] = field(default_factory=dict)
    history: Dict[Tuple[str, str], List[Candle]] = field(default_factory=dict)

    def get_current(self, symbol: str, timeframe: str) -> Optional[Candle]:
        return self.current.get((symbol, timeframe))

    def set_current(self, candle: Candle) -> None:
        self.current[(candle.symbol, candle.timeframe)] = candle

    def close_current(self, symbol: str, timeframe: str) -> Optional[Candle]:
        key = (symbol, timeframe)
        candle = self.current.pop(key, None)
        if candle is None:
            return None

        hist = self.history.setdefault(key, [])
        hist.append(candle)

        if len(hist) > self.max_history:
            del hist[:-self.max_history]

        return candle

    def get_history(self, symbol: str, timeframe: str) -> List[Candle]:
        return self.history.get((symbol, timeframe), [])
