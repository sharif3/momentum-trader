from __future__ import annotations

from datetime import datetime, timezone

from app.candles.builder import CandleBuilder
from app.models.market import Tick
from app.providers.base import MarketDataProvider


async def ws_ingest_loop(
    provider: MarketDataProvider,
    candle_builder: CandleBuilder,
    symbols: list[str],
) -> None:
    """
    Background loop:
    - reads tick dicts from provider.stream_ticks()
    - converts to Tick dataclass
    - updates candle builder (which updates the store)
    """
    async for msg in provider.stream_ticks(symbols):
        try:
            tick = Tick(
                symbol=msg["symbol"],
                price=msg["price"],
                size=msg["size"],
                ts=datetime.fromtimestamp(msg["t_ms"] / 1000.0, tz=timezone.utc),
            )
        except Exception:
            # Skip malformed tick messages
            continue

        candle_builder.on_tick(tick)

