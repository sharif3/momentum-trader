from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.state import store

router = APIRouter()


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@router.get("/snapshot")
def snapshot(ticker: str = Query(..., description="Ticker symbol, e.g., TSLA")):
    """
    Snapshot v1:
    - reports whether we have data for key timeframes
    - reports last_updated timestamps
    - reports simple freshness flags
    """
    symbol = ticker.upper()

    # For now, only 1m and 5m exist (from simulator/dev feed).
    # In Milestone 4 we’ll add 15m/1h/4h/1d from REST refresh.
    timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

    # Freshness thresholds (simple defaults for v1)
    # 1m should update frequently; allow 90s slack
    # 5m can be slower; allow 8 minutes slack
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

    return {
        "ticker": symbol,
        "timeframes": tf_status,
        "missing_timeframes": missing,
    }
import random
from datetime import datetime, timezone

from app.models.market import Tick
from app.state import builder


@router.post("/dev/simulate_tick")
def dev_simulate_tick(
    ticker: str = Query(..., description="Ticker symbol, e.g., TSLA"),
    price: float = Query(..., description="Tick price"),
    size: float = Query(10, description="Tick size/volume"),
):
    """
    Dev-only helper:
    Feeds ONE tick into the candle builder inside the running API process.
    This lets us test /snapshot without a real WebSocket yet.
    """
    tick = Tick(
        symbol=ticker.upper(),
        ts=datetime.now(timezone.utc),
        price=price,
        size=float(size),
    )

    closed = builder.on_tick(tick)
    return {"ok": True, "closed_count": len(closed)}
