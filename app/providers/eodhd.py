from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional

from app.providers.base import MarketDataProvider


class EodhdProvider(MarketDataProvider):
    """
    EODHD provider (stub).

    For now this is intentionally not implemented.
    We only need it to exist so the app can load the provider cleanly.
    """

    async def stream_ticks(self, symbols: List[str]) -> AsyncIterator[Dict]:
        raise NotImplementedError("EODHD WebSocket streaming not implemented yet")

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        raise NotImplementedError("EODHD REST candles fetch not implemented yet")
