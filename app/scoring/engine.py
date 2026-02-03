from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


from app.candles.store import CandleStore
from app.models.market_context import MarketContext

# Placeholder thresholds for v1 (documented, can be tuned later).
RS_RISK_OFF_THRESHOLD = 0.002  # 0.2% outperformance vs QQQ over 30m
NO_CHASE_ATR_MULTIPLE = 2.0

THIN_RELATIVE_VOLUME_THRESHOLD = 0.5  # Placeholder, EXT only
RTH_START = time(9, 30)
RTH_END = time(16, 0)
EASTERN = ZoneInfo("America/New_York")



def _last_close(store: CandleStore, symbol: str, timeframe: str) -> Optional[float]:
    candles = store.get_history(symbol, timeframe)
    if not candles:
        return None
    return float(candles[-1].c)

def _latest_price_ts(store: CandleStore, symbol: str) -> Optional[str]:
    for tf in ("1m", "5m", "15m"):
        ts = store.get_last_updated(symbol, tf)
        if ts is not None:
            return ts.isoformat()
    return None

def _latest_price_source(store: CandleStore, symbol: str) -> Optional[str]:
    if store.get_current(symbol, "1m") is not None:
        return "ws_1m"

    if _last_close(store, symbol, "1m") is not None:
        return "ws_1m_hist"

    if _last_close(store, symbol, "5m") is not None:
        return "ws_5m_hist"

    if _last_close(store, symbol, "15m") is not None:
        return "rest_15m_hist"

    return None

def _session_tag(ts_iso: Optional[str]) -> Optional[str]:
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    dt_et = dt.astimezone(EASTERN)
    if dt_et.weekday() >= 5:
        return "EXT"

    t = dt_et.time()
    return "RTH" if RTH_START <= t < RTH_END else "EXT"

def _count_gaps(candles: list, expected_seconds: int, max_check: int = 50) -> int:
    if len(candles) < 3:
        return 0

    tail = candles[-max_check:]
    gaps = 0

    for prev, curr in zip(tail, tail[1:]):
        delta = (curr.start_ts - prev.start_ts).total_seconds()

        # Out-of-order or duplicate timestamp
        if delta <= 0:
            gaps += 1
            continue

        # Ignore very large gaps (likely overnight/weekend)
        if delta > expected_seconds * 1.5 and delta < 7200:  # <2 hours
            gaps += 1

    return gaps

def _latest_price(store: CandleStore, symbol: str) -> Optional[float]:
    current_1m = store.get_current(symbol, "1m")
    if current_1m is not None:
        return float(current_1m.c)

    last_1m = _last_close(store, symbol, "1m")
    if last_1m is not None:
        return last_1m

    last_5m = _last_close(store, symbol, "5m")
    if last_5m is not None:
        return last_5m

    last_15m = _last_close(store, symbol, "15m")
    if last_15m is not None:
        return last_15m

    return None


def score_symbol(
    symbol: str,
    store: CandleStore,
    market_context: MarketContext,
    missing_timeframes: List[str],
    stale_timeframes: List[str],
    ema_5m: Dict[str, float],
    ema_15m: Dict[str, float],
    atr_5m: Dict[str, float],
    vwap_5m: Dict[str, float],
    atr_15m: Dict[str, float],
    prior_levels_15m: Dict[str, float],
    relvol_5m: Dict[str, float],
    relvol_15m: Dict[str, float],
) -> Dict[str, object]:

    audit: List[str] = []
    last_price = _latest_price(store, symbol)
    last_price_ts = _latest_price_ts(store, symbol)
    last_price_source = _latest_price_source(store, symbol)



    # Hard rule: required timeframes must exist.
    if "5m" in missing_timeframes or "15m" in missing_timeframes:
        missing_required = [tf for tf in ("5m", "15m") if tf in missing_timeframes]
        audit.append(f"missing required timeframe(s): {', '.join(missing_required)}")
        return {
            "signal": "HOLD",
            "last_price": last_price,
            "last_price_ts": last_price_ts,
            "last_price_source": last_price_source,
            "state": "NO_MOMO",
            "confidence": 0.0,
            "suggested_size": 0.0,
            "levels": {
                "entry_range": None,
                "stop": None,
                "targets": [],
                "support_range": None,
                "resistance_1": None,
                "resistance_2": None,
            },
            "audit": audit,
        }

    if "5m" in stale_timeframes or "15m" in stale_timeframes:
        stale_required = [tf for tf in ("5m", "15m") if tf in stale_timeframes]
        audit.append(f"stale required timeframe(s): {', '.join(stale_required)}")
        return {
            "signal": "HOLD",
            "last_price": last_price,
            "last_price_ts": last_price_ts,
            "last_price_source": last_price_source,
            "state": "NO_MOMO",
            "confidence": 0.0,
            "suggested_size": 0.0,
            "levels": {
                "entry_range": None,
                "stop": None,
                "targets": [],
                "support_range": None,
                "resistance_1": None,
                "resistance_2": None,
            },
            "audit": audit,
        }
    
    gaps_5m = _count_gaps(store.get_history(symbol, "5m"), expected_seconds=300)
    gaps_15m = _count_gaps(store.get_history(symbol, "15m"), expected_seconds=900)

    if gaps_5m > 2 or gaps_15m > 2:
        audit.append(f"gap_check: too many gaps (5m={gaps_5m}, 15m={gaps_15m})")
        return {
            "signal": "HOLD",
            "last_price": last_price,
            "last_price_ts": last_price_ts,
            "last_price_source": last_price_source,
            "state": "NO_MOMO",
            "confidence": 0.0,
            "suggested_size": 0.0,
            "levels": {
                "entry_range": None,
                "stop": None,
                "targets": [],
                "support_range": None,
                "resistance_1": None,
                "resistance_2": None,
            },
            "audit": audit,
        }
    
    session = _session_tag(last_price_ts)
    relvol_value = relvol_15m.get("relvol20") or relvol_5m.get("relvol20")

    if session == "EXT":
        if relvol_value is None:
            audit.append("thin_volume_gate: skipped (missing relvol)")
        elif relvol_value < THIN_RELATIVE_VOLUME_THRESHOLD:
            audit.append(
                f"thin_volume_gate: fail (session=EXT, relvol20={relvol_value:.3f} < {THIN_RELATIVE_VOLUME_THRESHOLD})"
            )
            return {
                "signal": "HOLD",
                "last_price": last_price,
                "last_price_ts": last_price_ts,
                "last_price_source": last_price_source,
                "state": "NO_MOMO",
                "confidence": 0.0,
                "suggested_size": 0.0,
                "levels": {
                    "entry_range": None,
                    "stop": None,
                    "targets": [],
                    "support_range": None,
                    "resistance_1": None,
                    "resistance_2": None,
                },
                "audit": audit,
            }
        else:
            audit.append(f"thin_volume_gate: pass (session=EXT, relvol20={relvol_value:.3f})")

    # --- Minimal state machine (current-state snapshot) ---
    ema9_5m = ema_5m.get("ema9")
    ema20_5m = ema_5m.get("ema20")
    ema9_15m = ema_15m.get("ema9")
    ema20_15m = ema_15m.get("ema20")
    ema50_15m = ema_15m.get("ema50")

    last_close_5m = _last_close(store, symbol, "5m")

    state = "BUILDING"
    if None in (ema9_5m, ema20_5m, ema9_15m, ema20_15m):
        audit.append("state: missing EMA inputs (5m/15m)")
        state = "NO_MOMO"
    else:
        if ema9_5m > ema20_5m and ema9_15m > ema20_15m:
            state = "ACTIVE"
        elif ema9_5m < ema20_5m and ema9_15m < ema20_15m:
            state = "FAILING"
        else:
            state = "BUILDING"

    if state == "FAILING" and ema50_15m is not None and last_close_5m is not None:
        if last_close_5m < ema50_15m:
            state = "FAILED"

    # --- Gates ---
    gates_pass = True

    # Tape gate: risk_off suppresses BUY unless RS_30m is strong enough.
    if market_context.risk_off:
        rs = market_context.rs_30m
        if rs is None or rs <= RS_RISK_OFF_THRESHOLD:
            gates_pass = False
            audit.append(
                f"tape_gate: fail (risk_off, rs_30m={rs}, threshold={RS_RISK_OFF_THRESHOLD})"
            )
        else:
            audit.append(
                f"tape_gate: pass (risk_off but rs_30m={rs} > {RS_RISK_OFF_THRESHOLD})"
            )

    # No-chase gate: distance from anchor <= 2 * ATR(14, 5m)
    atr14 = atr_5m.get("atr14")
    anchor = vwap_5m.get("vwap50") or ema_5m.get("ema20")

    if atr14 is None or anchor is None or last_close_5m is None:
        audit.append("no_chase_gate: skipped (missing atr/anchor/last_close)")
    else:
        distance = abs(last_close_5m - float(anchor))
        limit = NO_CHASE_ATR_MULTIPLE * float(atr14)
        if distance > limit:
            gates_pass = False
            audit.append(
                f"no_chase_gate: fail (distance={distance:.4f} > {NO_CHASE_ATR_MULTIPLE}*ATR)"
            )
        else:
            audit.append(
                f"no_chase_gate: pass (distance={distance:.4f} <= {NO_CHASE_ATR_MULTIPLE}*ATR)"
            )
        entry_range = None
    stop = None
    targets: List[float] = []

    if atr14 is not None and anchor is not None:
        entry_low = float(anchor) - 0.25 * float(atr14)
        entry_high = float(anchor) + 0.25 * float(atr14)
        entry_range = [float(entry_low), float(entry_high)]

        entry_mid = (entry_low + entry_high) / 2.0
        stop = float(entry_mid - 1.2 * float(atr14))
        targets = [
            float(entry_mid + 1.5 * float(atr14)),
            float(entry_mid + 2.5 * float(atr14)),
        ]
    support_range = None
    resistance_1 = None
    resistance_2 = None

    prior_low20 = prior_levels_15m.get("prior_low20")
    prior_high20 = prior_levels_15m.get("prior_high20")
    atr15 = atr_15m.get("atr14")

    if prior_low20 is not None:
        if atr15 is not None:
            support_range = [
                float(prior_low20),
                float(prior_low20 + 0.25 * atr15),
            ]
        else:
            support_range = [float(prior_low20), float(prior_low20)]

    if prior_high20 is not None:
        if atr15 is not None:
            resistance_1 = [
                float(prior_high20 - 0.25 * atr15),
                float(prior_high20 + 0.25 * atr15),
            ]
            resistance_2 = [
                float(prior_high20 + 0.75 * atr15),
                float(prior_high20 + 1.25 * atr15),
            ]
        else:
            resistance_1 = [float(prior_high20), float(prior_high20)]


    # --- Decision mapping ---
    signal = "HOLD"
    if state in ("FAILING", "FAILED"):
        signal = "EXIT"
    elif state == "ACTIVE" and gates_pass:
        signal = "BUY"

    # --- Confidence / size (minimal placeholders) ---
    confidence = 0.0
    suggested_size = 0.0
    if signal == "BUY":
        confidence = 0.35
        suggested_size = 0.25
    elif state == "ACTIVE":
        confidence = 0.2
    elif state == "BUILDING":
        confidence = 0.1

    return {
        "signal": signal,
        "state": state,
        "confidence": float(confidence),
        "suggested_size": float(suggested_size),
        "levels": {
            "entry_range": entry_range,
            "stop": stop,
            "targets": targets,
            "support_range": support_range,
            "resistance_1": resistance_1,
            "resistance_2": resistance_2,
        },
        "audit": audit,
        "last_price": last_price,
        "last_price_ts": last_price_ts,
        "last_price_source": last_price_source,


    }
