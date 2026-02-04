from __future__ import annotations

import time
from typing import List, Optional, Tuple

from app.indicators.engine import compute_ema_for_timeframe
from app.models.market import Candle
from app.models.market_context import MarketContext
from app.providers.loader import get_provider
from app.state import store

# Simple in-memory cache to reduce REST calls.
# Key: (symbol, n_bars) -> (cached_at_epoch_seconds, pct_return)
_RET_CACHE: dict[tuple[str, int], tuple[float, float]] = {}
_RET_CACHE_TTL_SECONDS = 60

def _pct_return_from_store_5m(symbol: str, n: int = 6) -> float | None:
    candles_5m = store.get_history(symbol, "5m") or []
    if len(candles_5m) < (n + 1):
        return None

    close_now = float(candles_5m[-1].c)
    close_then = float(candles_5m[-(n + 1)].c)
    if close_then == 0:
        return None

    return float((close_now / close_then) - 1.0)


def _pct_return_last_n_5m(symbol: str, n: int = 6) -> float | None:
    # 0) Use WS-built 5m if available
    store_ret = _pct_return_from_store_5m(symbol, n=n)
    if store_ret is not None:
        return store_ret

    # 1) Cache check
    key = (symbol, n)
    now = time.time()
    cached = _RET_CACHE.get(key)
    if cached:
        cached_at, cached_val = cached
        if (now - cached_at) <= _RET_CACHE_TTL_SECONDS:
            return cached_val

    # 2) REST fetch (fallback until WS 5m exists)
    provider = get_provider()


    # Need n+1 closes to compute return over n bars
    rows = provider.fetch_candles(symbol, "5m", limit=max(50, n + 10))
    if not rows or len(rows) < (n + 1):
        return None

    close_now = float(rows[-1]["close"])
    close_then = float(rows[-(n + 1)]["close"])
    if close_then == 0:
        return None

    ret = (close_now / close_then) - 1.0

    # 3) Store cache
    _RET_CACHE[key] = (now, float(ret))
    return float(ret)


def _min_low(candles: List[Candle]) -> float:
    return min(c.l for c in candles)


def _risk_flag(symbol: str) -> Tuple[bool, List[str]]:
    """
    Returns:
      (flag, audit_reasons)

    flag=True means this symbol is in a "risk-off" posture per our simple 15m rule.
    """
    audit: List[str] = []

    candles_15m = store.get_history(symbol, "15m") or []
    if len(candles_15m) < 24:
        audit.append(
            f"{symbol}: not enough 15m candles (need>=24, have={len(candles_15m)})"
        )
        return False, audit

    ema_map = compute_ema_for_timeframe(store, symbol, "15m", periods=[20])
    ema20 = ema_map.get("ema20")
    if ema20 is None:
        audit.append(f"{symbol}: missing EMA20(15m)")
        return False, audit

    close_now = float(candles_15m[-1].c)

    below_ema20 = close_now < float(ema20)
    audit.append(f"{symbol}: close<ema20={below_ema20}")

    last12 = candles_15m[-12:]
    prev12 = candles_15m[-24:-12]
    lower_lows = _min_low(last12) < _min_low(prev12)
    audit.append(f"{symbol}: lower_lows_12={lower_lows}")

    close_3ago = float(candles_15m[-4].c)
    slope_down_proxy = close_now < close_3ago
    audit.append(f"{symbol}: slope_down_proxy={slope_down_proxy}")

    flag = below_ema20 and lower_lows and slope_down_proxy
    audit.append(f"{symbol}: risk_flag={flag}")
    return flag, audit


def compute_market_context(primary_symbol: str) -> MarketContext:
    """
    Computes tape regime using SPY.US + QQQ.US 15m candles.

    This version computes:
      - regime (RISK_ON / NEUTRAL / RISK_OFF / UNKNOWN)
      - risk_off boolean
      - rs_30m (relative strength vs QQQ over last 30m using 5m REST candles)
    """
    spy = "SPY.US"
    qqq = "QQQ.US"

    audit: List[str] = []

    ticker_ret = _pct_return_last_n_5m(primary_symbol, n=6)
    qqq_ret = _pct_return_last_n_5m(qqq, n=6)

    rs_30m: Optional[float] = None
    if ticker_ret is None or qqq_ret is None:
        audit.append("RS_30m: insufficient 5m data via REST fallback")
    else:
        rs_30m = float(ticker_ret - qqq_ret)
        audit.append(f"RS_30m: {rs_30m:.6f}")

    spy_has = store.has_any_data(spy, "15m")
    qqq_has = store.has_any_data(qqq, "15m")

    if not spy_has or not qqq_has:
        if not spy_has:
            audit.append("SPY.US: missing 15m data")
        if not qqq_has:
            audit.append("QQQ.US: missing 15m data")
        return MarketCo
