# app/api/routes.py
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Query

from app.state import store
from app.indicators.engine import (
    compute_ema_for_timeframe,
    compute_atr_for_timeframe,
    compute_prior_high_low,
    compute_obv_slope_for_timeframe,
    compute_vwap_for_timeframe,
    compute_relvol_for_timeframe,
)

router = APIRouter()

TF_MAX_AGE_SECONDS: Dict[str, int] = {
    "1m": 90,
    "5m": 480,
    "15m": 1200,
    "1h": 5400,
    "4h": 21600,
    "1d": 129600,
}


def _tf_status(symbol: str, tf: str) -> Dict:
    max_age = TF_MAX_AGE_SECONDS[tf]
    last = store.get_last_updated(symbol, tf)
    return {
        "has_data": store.has_any_data(symbol, tf),
        "last_updated": last.isoformat() if last else None,
        "fresh": store.is_fresh(symbol, tf, max_age_seconds=max_age),
        "max_age_seconds": max_age,
    }


@router.get("/snapshot")
def snapshot(
    ticker: str = Query(..., description="Symbol, e.g. TSLA.US"),
    limit: int = Query(50, ge=10, le=500, description="(Reserved) Max candles to return later"),
):
    symbol = ticker.upper().strip()

    timeframes = {tf: _tf_status(symbol, tf) for tf in TF_MAX_AGE_SECONDS.keys()}
    missing = [tf for tf, info in timeframes.items() if not info["has_data"]]

    ema = {
        "1m": compute_ema_for_timeframe(store, symbol, "1m", periods=[9, 20]),
        "5m": compute_ema_for_timeframe(store, symbol, "5m", periods=[9, 20]),
        "15m": compute_ema_for_timeframe(store, symbol, "15m", periods=[9, 20, 50, 200]),
        "1h": compute_ema_for_timeframe(store, symbol, "1h", periods=[50, 200]),
        "1d": compute_ema_for_timeframe(store, symbol, "1d", periods=[50, 200]),
    }

    atr = {
        "5m": compute_atr_for_timeframe(store, symbol, "5m", period=14),
        "15m": compute_atr_for_timeframe(store, symbol, "15m", period=14),
    }

    prior_levels = {
        "5m": compute_prior_high_low(store, symbol, "5m", window=20),
        "15m": compute_prior_high_low(store, symbol, "15m", window=20),
    }

    obv = {
        "5m": compute_obv_slope_for_timeframe(store, symbol, "5m", window=20),
        "15m": compute_obv_slope_for_timeframe(store, symbol, "15m", window=20),
    }

    vwap = {
        "5m": compute_vwap_for_timeframe(store, symbol, "5m", window=50),
        "15m": compute_vwap_for_timeframe(store, symbol, "15m", window=50),
    }

    relvol = {
        "5m": compute_relvol_for_timeframe(store, symbol, "5m", window=20),
        "15m": compute_relvol_for_timeframe(store, symbol, "15m", window=20),
    }

    return {
        "ticker": symbol,
        "timeframes": timeframes,
        "missing_timeframes": missing,
        "indicators": {
            "ema": ema,
            "atr": atr,
            "prior_levels": prior_levels,
            "obv": obv,
            "vwap": vwap,
            "relvol": relvol,
        },
    }


@router.get("/score")
def score(
    ticker: str = Query(..., description="Symbol, e.g. TSLA.US"),
):
    symbol = ticker.upper().strip()

    timeframes = {tf: _tf_status(symbol, tf) for tf in TF_MAX_AGE_SECONDS.keys()}
    missing = [tf for tf, info in timeframes.items() if not info["has_data"]]

    ema_5m = compute_ema_for_timeframe(store, symbol, "5m", periods=[9, 20])
    ema_15m = compute_ema_for_timeframe(store, symbol, "15m", periods=[9, 20, 50, 200])
    ema_1h = compute_ema_for_timeframe(store, symbol, "1h", periods=[50, 200])
    ema_1d = compute_ema_for_timeframe(store, symbol, "1d", periods=[50, 200])

    atr_5m = compute_atr_for_timeframe(store, symbol, "5m", period=14)
    atr_15m = compute_atr_for_timeframe(store, symbol, "15m", period=14)

    obv_5m = compute_obv_slope_for_timeframe(store, symbol, "5m", window=20)
    obv_15m = compute_obv_slope_for_timeframe(store, symbol, "15m", window=20)

    vwap_5m = compute_vwap_for_timeframe(store, symbol, "5m", window=50)
    vwap_15m = compute_vwap_for_timeframe(store, symbol, "15m", window=50)

    relvol_5m = compute_relvol_for_timeframe(store, symbol, "5m", window=20)
    relvol_15m = compute_relvol_for_timeframe(store, symbol, "15m", window=20)

    if "5m" in missing or "15m" in missing:
        return {
            "ticker": symbol,
            "signal": "HOLD",
            "state": "NO_MOMO",
            "confidence": 0.0,
            "suggested_size": 0.0,
            "missing_timeframes": missing,
            "timeframes": timeframes,
            "tape": {"risk_off": None, "rs_30m": None},
            "levels": {"entry": None, "stop": None, "targets": []},
            "indicators": {
                "ema": {"5m": ema_5m, "15m": ema_15m, "1h": ema_1h, "1d": ema_1d},
                "atr": {"5m": atr_5m, "15m": atr_15m},
                "obv": {"5m": obv_5m, "15m": obv_15m},
                "vwap": {"5m": vwap_5m, "15m": vwap_15m},
                "relvol": {"5m": relvol_5m, "15m": relvol_15m},
            },
            "audit": ["missing required timeframe(s): 5m and/or 15m"],
        }

    return {
        "ticker": symbol,
        "signal": "HOLD",
        "state": "BUILDING",
        "confidence": 0.1,
        "suggested_size": 0.0,
        "missing_timeframes": missing,
        "timeframes": timeframes,
        "tape": {"risk_off": None, "rs_30m": None},
        "levels": {"entry": None, "stop": None, "targets": []},
        "indicators": {
            "ema": {"5m": ema_5m, "15m": ema_15m, "1h": ema_1h, "1d": ema_1d},
            "atr": {"5m": atr_5m, "15m": atr_15m},
            "obv": {"5m": obv_5m, "15m": obv_15m},
            "vwap": {"5m": vwap_5m, "15m": vwap_15m},
            "relvol": {"5m": relvol_5m, "15m": relvol_15m},
        },
        "audit": ["placeholder scoring engine (Milestone 7 will replace)"],
    }
