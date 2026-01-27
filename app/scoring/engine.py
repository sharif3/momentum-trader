from __future__ import annotations

from typing import Dict, List, Optional

from app.candles.store import CandleStore
from app.models.market_context import MarketContext

# Placeholder thresholds for v1 (documented, can be tuned later).
RS_RISK_OFF_THRESHOLD = 0.002  # 0.2% outperformance vs QQQ over 30m
NO_CHASE_ATR_MULTIPLE = 2.0


def _last_close(store: CandleStore, symbol: str, timeframe: str) -> Optional[float]:
    candles = store.get_history(symbol, timeframe)
    if not candles:
        return None
    return float(candles[-1].c)


def score_symbol(
    symbol: str,
    store: CandleStore,
    market_context: MarketContext,
    missing_timeframes: List[str],
    ema_5m: Dict[str, float],
    ema_15m: Dict[str, float],
    atr_5m: Dict[str, float],
    vwap_5m: Dict[str, float],
) -> Dict[str, object]:
    audit: List[str] = []

    # Hard rule: required timeframes must exist.
    if "5m" in missing_timeframes or "15m" in missing_timeframes:
        missing_required = [tf for tf in ("5m", "15m") if tf in missing_timeframes]
        audit.append(f"missing required timeframe(s): {', '.join(missing_required)}")
        return {
            "signal": "HOLD",
            "state": "NO_MOMO",
            "confidence": 0.0,
            "suggested_size": 0.0,
            "levels": {"entry_range": None, "stop": None, "targets": []},
            "audit": audit,
        }

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
        "levels": {"entry_range": None, "stop": None, "targets": []},
        "audit": audit,
    }
