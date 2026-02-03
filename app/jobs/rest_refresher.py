from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import timedelta

import httpx

from app.models.market import Candle
from app.providers.loader import get_provider
from app.state import store


def _bucket_start_4h(dt):
    hour = (dt.hour // 4) * 4
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def _aggregate_1h_to_4h(symbol: str, c1h: list[Candle], limit_4h: int) -> list[Candle]:
    c4h: list[Candle] = []
    bucket: list[Candle] = []

    for c in c1h:
        if not bucket:
            bucket = [c]
            continue

        if _bucket_start_4h(c.start_ts) == _bucket_start_4h(bucket[0].start_ts):
            bucket.append(c)
        else:
            first = bucket[0]
            last = bucket[-1]
            start = _bucket_start_4h(first.start_ts)
            c4h.append(
                Candle(
                    symbol=symbol,
                    timeframe="4h",
                    start_ts=start,
                    end_ts=start + timedelta(hours=4),
                    o=first.o,
                    h=max(x.h for x in bucket),
                    l=min(x.l for x in bucket),
                    c=last.c,
                    v=sum(x.v for x in bucket),
                )
            )
            bucket = [c]

    if bucket:
        first = bucket[0]
        last = bucket[-1]
        start = _bucket_start_4h(first.start_ts)
        c4h.append(
            Candle(
                symbol=symbol,
                timeframe="4h",
                start_ts=start,
                end_ts=start + timedelta(hours=4),
                o=first.o,
                h=max(x.h for x in bucket),
                l=min(x.l for x in bucket),
                c=last.c,
                v=sum(x.v for x in bucket),
            )
        )

    return c4h[-limit_4h:]

def _drop_partial(candles: list[Candle], now_utc) -> list[Candle]:
    if not candles:
        return candles
    last = candles[-1]
    # If candle end is in the future, it is still forming -> drop it.
    if last.end_ts > now_utc:
        return candles[:-1]
    return candles


async def rest_refresh_loop(symbol: str) -> None:
    """
    Background loop:
    periodically refresh 15m/1h/1d (and 4h via fallback) into the in-memory store.
    """
    provider = get_provider()
    log = logging.getLogger("rest_refresher")

    while True:
        try:
            # Fetch raw dicts
            candles_15m = provider.fetch_candles(symbol, "15m", 300)
            candles_1h = provider.fetch_candles(symbol, "1h", 300)
            candles_1d = provider.fetch_candles(symbol, "1d", 300)
            log.info(
                "Fetched counts symbol=%s 15m=%d 1h=%d 1d=%d",
                symbol,
                len(candles_15m),
                len(candles_1h),
                len(candles_1d),
            )

            # Convert to Candle objects
            def to_candle(tf: str, row: dict, duration: timedelta) -> Candle:
                start_ts = row["ts"]
                return Candle(
                    symbol=symbol,
                    timeframe=tf,
                    start_ts=start_ts,
                    end_ts=start_ts + duration,
                    o=row["open"],
                    h=row["high"],
                    l=row["low"],
                    c=row["close"],
                    v=row["volume"],
                )

            c15m = [to_candle("15m", r, timedelta(minutes=15)) for r in candles_15m]
            c1h = [to_candle("1h", r, timedelta(hours=1)) for r in candles_1h]
            c1d = [to_candle("1d", r, timedelta(days=1)) for r in candles_1d]

            # Try REST 4h; fallback to aggregation
            try:
                candles_4h = provider.fetch_candles(symbol, "4h", 300)
                c4h = [to_candle("4h", r, timedelta(hours=4)) for r in candles_4h]
            except httpx.HTTPStatusError:
                c4h = _aggregate_1h_to_4h(symbol, c1h, 300)

            now_utc = datetime.now(timezone.utc)
            c15m = _drop_partial(c15m, now_utc)
            c1h = _drop_partial(c1h, now_utc)
            c4h = _drop_partial(c4h, now_utc)
            c1d = _drop_partial(c1d, now_utc)


            log.info("Fetched counts symbol=%s 4h=%d", symbol, len(c4h))

            store.replace_history(symbol, "15m", c15m)
            store.replace_history(symbol, "1h", c1h)
            store.replace_history(symbol, "4h", c4h)
            store.replace_history(symbol, "1d", c1d)

        except Exception as e:
            # Keep loop alive even if provider temporarily fails, but log the error.
            log.error("REST refresh failed for symbol=%s error=%s", symbol, repr(e))
            log.error(traceback.format_exc())

        # Refresh cadence: every 60s for now (simple).
        await asyncio.sleep(60)
