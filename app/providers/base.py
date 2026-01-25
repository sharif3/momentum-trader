from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional


class MarketDataProvider(ABC):
    """
    Provider contract (interface).

    Any provider must implement:
    - stream_ticks(): live ticks via WebSocket (async iterator)
    - fetch_candles(): historical candles via REST
    """

    @abstractmethod
    async def stream_ticks(self, symbols: List[str]) -> AsyncIterator[Dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        raise NotImplementedError
