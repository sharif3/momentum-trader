from __future__ import annotations

from typing import Dict, List

from app.candles.store import CandleStore

def _has_gaps(candles: list, expected_seconds: int, max_check: int = 50) -> bool:
    if len(candles) < 3:
        return False

    tail = candles[-max_check:]
    for prev, curr in zip(tail, tail[1:]):
        delta = (curr.start_ts - prev.start_ts).total_seconds()
        if delta <= 0:
            return True
        if delta > expected_seconds * 1.5 and delta < 7200:
            return True
    return False

# -------------------------
# EMA
# -------------------------
def ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append((v - out[-1]) * k + out[-1])
    return out


def compute_ema_for_timeframe(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    periods: List[int],
) -> Dict[str, float]:
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    closes = [c.c for c in candles]

    result: Dict[str, float] = {}
    for p in periods:
        series = ema_series(closes, p)
        if series:
            result[f"ema{p}"] = float(series[-1])
    return result


# -------------------------
# ATR
# -------------------------
def true_range_series(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    if len(highs) < 2 or len(lows) < 2 or len(closes) < 2:
        return []
    tr: List[float] = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr.append(max(hl, hc, lc))
    return tr


def compute_atr_for_timeframe(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    period: int = 14,
) -> Dict[str, float]:
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    highs = [c.h for c in candles]
    lows = [c.l for c in candles]
    closes = [c.c for c in candles]

    tr = true_range_series(highs, lows, closes)
    if len(tr) < period:
        return {}
    atr = sum(tr[-period:]) / period
    return {f"atr{period}": float(atr)}


# -------------------------
# PriorHigh / PriorLow
# -------------------------
def compute_prior_high_low(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    window: int = 20,
) -> Dict[str, float]:
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    if len(candles) < window + 1:
        return {}
    lookback = candles[-(window + 1) : -1]
    prior_high = max(c.h for c in lookback)
    prior_low = min(c.l for c in lookback)
    return {
        f"prior_high{window}": float(prior_high),
        f"prior_low{window}": float(prior_low),
    }


# -------------------------
# OBV + OBV slope
# -------------------------
def obv_series(closes: List[float], volumes: List[float]) -> List[float]:
    if len(closes) < 2 or len(volumes) < 2:
        return []
    obv: List[float] = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def linear_slope(y: List[float]) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    sum_x = (n - 1) * n / 2.0
    sum_x2 = (n - 1) * n * (2 * n - 1) / 6.0
    sum_y = sum(y)
    sum_xy = sum(i * y[i] for i in range(n))
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def compute_obv_slope_for_timeframe(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    window: int = 20,
) -> Dict[str, float]:
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    closes = [c.c for c in candles]
    vols = [c.v for c in candles]

    series = obv_series(closes, vols)
    if not series:
        return {}
    if len(series) < window:
        return {"obv": float(series[-1])}

    tail = series[-window:]
    slope = linear_slope(tail)
    return {"obv": float(series[-1]), f"obv_slope{window}": float(slope)}


# -------------------------
# VWAP (rolling approximation for v1)
# -------------------------
def compute_vwap_for_timeframe(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    window: int = 50,
) -> Dict[str, float]:
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    if len(candles) < 2:
        return {}

    lookback = candles[-window:] if len(candles) >= window else candles

    pv_sum = 0.0
    v_sum = 0.0
    for c in lookback:
        if c.v is None or c.v <= 0:
            continue
        typical = (c.h + c.l + c.c) / 3.0
        pv_sum += typical * c.v
        v_sum += c.v

    if v_sum <= 0:
        return {}
    return {f"vwap{window}": float(pv_sum / v_sum)}


# -------------------------
# Relative Volume (basic)
# -------------------------
def compute_relvol_for_timeframe(
    store: CandleStore,
    symbol: str,
    timeframe: str,
    window: int = 20,
) -> Dict[str, float]:
    """
    Basic relative volume:
      relvol = last_candle_volume / avg(volume over last `window` candles)

    Uses CLOSED candles.
    """
    candles = store.get_history(symbol, timeframe)
    if timeframe in ("5m", "15m") and _has_gaps(candles, 300 if timeframe == "5m" else 900):
        return {}
    if len(candles) < window:
        return {}

    vols = [c.v for c in candles[-window:]]
    avg = sum(vols) / window if window > 0 else 0.0
    if avg <= 0:
        return {}

    last_v = candles[-1].v
    return {f"relvol{window}": float(last_v / avg)}
