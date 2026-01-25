from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Query

from app.models.market import Candle, Tick
from app.providers.loader import get_provider
from app.state import builder, store

router = APIRouter()


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@router.get("/snapshot")
def snapshot(ticker: str = Query(..., description="Ticker symbol, e.g., TSLA or TSLA.US")):
    """
    Snapshot v1:
    - reports whether we have data for key timeframes
    - reports last_updated timestamps
    - reports simple freshness flags
    """
    symbol = ticker.upper()

    timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

    freshness_seconds = {
        "1m": 90,
        "5m": 8 * 60,
        "15m": 20 * 60,
        "1h": 90 * 60,
        "4h": 6 * 60 * 60,
        "1d": 36 * 60 * 60,
    }

    tf_status = {}
    missing = []

    for tf in timeframes:
        has_data = store.has_any_data(symbol, tf)
        last = store.get_last_updated(symbol, tf)
        is_fresh = store.is_fresh(symbol, tf, freshness_seconds[tf])

        tf_status[tf] = {
            "has_data": has_data,
            "last_updated": iso(last),
            "fresh": is_fresh,
            "max_age_seconds": freshness_seconds[tf],
        }

        if not has_data:
            missing.append(tf)

    return {"ticker": symbol, "timeframes": tf_status, "missing_timeframes": missing}


@router.post("/dev/simulate_tick")
def dev_simulate_tick(
    ticker: str = Query(..., description="Ticker symbol, e.g., TSLA"),
    price: float = Query(..., description="Tick price"),
    size: float = Query(10, description="Tick size/volume"),
):
    """
    Dev-only helper:
    Feeds ONE tick into the candle builder inside the running API process.
    """
    tick = Tick(
        symbol=ticker.upper(),
        ts=datetime.now(timezone.utc),
        price=price,
        size=float(size),
    )
    closed = builder.on_tick(tick)
    return {"ok": True, "closed_count": len(closed)}


@router.post("/dev/refresh_rest")
def dev_refresh_rest(
    ticker: str = Query(..., description="EODHD symbol, e.g., TSLA.US"),
    limit_15m: int = Query(300, description="How many 15m candles to fetch"),
    limit_1h: int = Query(300, description="How many 1h candles to fetch"),
    limit_4h: int = Query(300, description="How many 4h candles to store"),
    limit_1d: int = Query(300, description="How many 1d candles to fetch"),
):
    """
    Dev-only helper:
    Fetch 15m/1h/1d via REST and store them.
    For 4h: try REST first; if provider errors, fallback to aggregating 1h -> 4h.
    """
    symbol = ticker.upper()
    provider = get_provider()

    candles_15m = provider.fetch_candles(symbol, "15m", limit_15m)
    candles_1h = provider.fetch_candles(symbol, "1h", limit_1h)
    candles_1d = provider.fetch_candles(symbol, "1d", limit_1d)

    # Try REST 4h; fallback to 1h aggregation if it errors (EODHD returns 500 for some symbols).
    fourh_source = "rest"
    candles_4h = []
    try:
        candles_4h = provider.fetch_candles(symbol, "4h", limit_4h)
    except httpx.HTTPStatusError:
        fourh_source = "agg_1h"

    def to_candle(tf: str, row: dict, duration: timedelta) -> Candle:
        start_ts = row["ts"]
        end_ts = start_ts + duration
        return Candle(
            symbol=symbol,
            timeframe=tf,
            start_ts=start_ts,
            end_ts=end_ts,
            o=row["open"],
            h=row["high"],
            l=row["low"],
            c=row["close"],
            v=row["volume"],
        )

    c15m = [to_candle("15m", r, timedelta(minutes=15)) for r in candles_15m]
    c1h = [to_candle("1h", r, timedelta(hours=1)) for r in candles_1h]
    c1d = [to_candle("1d", r, timedelta(days=1)) for r in candles_1d]

    # 4h candles
    if fourh_source == "rest":
        c4h = [to_candle("4h", r, timedelta(hours=4)) for r in candles_4h]
    else:
        c4h = []

        def bucket_start(dt: datetime) -> datetime:
            hour = (dt.hour // 4) * 4
            return dt.replace(hour=hour, minute=0, second=0, microsecond=0)

        bucket: list[Candle] = []
        for c in c1h:
            if not bucket:
                bucket = [c]
                continue

            if bucket_start(c.start_ts) == bucket_start(bucket[0].start_ts):
                bucket.append(c)
            else:
                first = bucket[0]
                last = bucket[-1]
                start = bucket_start(first.start_ts)
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
            start = bucket_start(first.start_ts)
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

        c4h = c4h[-limit_4h:]

    store.replace_history(symbol, "15m", c15m)
    store.replace_history(symbol, "1h", c1h)
    store.replace_history(symbol, "4h", c4h)
    store.replace_history(symbol, "1d", c1d)

    return {
        "ok": True,
        "ticker": symbol,
        "stored": {"15m": len(c15m), "1h": len(c1h), "4h": len(c4h), "1d": len(c1d)},
        "meta": {"4h_source": fourh_source},
    }
