# Momentum Trader (v1) — PRD

## 1) What we’re building (in plain English)
A local-running backend service that:
- listens to live price updates (ticks) from a market data provider (WebSocket)
- converts those ticks into candles (1m, 5m) in real time
- keeps higher timeframe candles (15m, 1h, 4h, 1d) updated via REST
- computes indicators per timeframe
- applies deterministic momentum rules to output: BUY / HOLD / EXIT + confidence/size + risk levels
- exposes REST endpoints that GPT Actions can call (GPT does not stream ticks)

## 2) Key constraints
- Start minimal: **one ticker**, local run.
- No broker execution in v1 (no placing orders).
- No hardcoded secrets. API keys only via `.env`.
- Provider must be swappable (we’ll start with **EODHD** but design for plug-and-play).

## 3) Data sources (provider-agnostic)
We support a single “Market Data Provider” interface with two capabilities:
1) WebSocket: live ticks (used for near-real-time intraday timing)
2) REST: historical & higher timeframe candles (used for 15m/1h/4h/1d backfill + refresh)

Initial provider implementation: **EODHD** (REST + WebSocket).
Design must allow adding TwelveData / Polygon / Alpaca etc later without rewriting the core.

## 4) Instruments (v1)
- Primary ticker: user-supplied (e.g., TSLA)
- Tape context tickers (hardcoded for now): **SPY and QQQ**
  - Used to compute market risk regime + relative strength

## 5) Timeframes we must support
Candles (OHLCV):
- Intraday built from WebSocket: **1m, 5m**
- Higher TF from REST (and refreshed): **15m, 1h, 4h, 1d**

Special handling:
- 15m “current forming” candle can be built from 1m candles for near real-time structure checks.
- Closed 15m candles come from REST (more reliable for completed bars).

Minimum required for intraday signals:
- Must have valid **5m and 15m**. If missing -> return HOLD + list missing timeframes.
- 1h/1d are “context bonuses” for intraday (not required to trade intraday), but used for swing/hold context later.

## 6) Validation rules (to avoid bad signals)
We do not score if data is invalid.
Validation examples:
- Candle timestamps are aligned to timeframe boundaries
- No future timestamps
- Drop partial / incomplete REST candles (if provider returns them)
- Detect gaps (missing bars) and mark that timeframe stale
- Tag candles as RTH vs EXT (regular trading hours vs extended) where possible

## 7) Indicators to compute (v1)
Intraday trend & structure:
- EMA(9), EMA(20) on: 1m / 5m / 15m
- EMA(50), EMA(200) on: 15m / 1h / 1d
- VWAP intraday (RTH session). If VWAP not available, use EMA20 as the “anchor”.
- PriorHigh20 / PriorLow20 on: 5m and 15m
- Swing-low proxy on 15m: lowest low of last 20 candles

Participation / flow:
- Relative Volume (RelVol): RTH and EXT flavors (or a single version if session split not available yet)
- OBV slope on: 5m and 15m

Risk:
- ATR(14) on: 5m and 15m
- (Optional later) ATR30

Optional-only (not required for v1):
- RSI (mainly to avoid chasing)
- MACD (mainly swing context)

## 8) Tape context calculations (v1)
Market RiskOff:
- Derived from SPY + QQQ 15m conditions (e.g., below EMA20 and making lower lows over a window).
Relative Strength (RS_30m):
- RS_30m = (ticker 5m return over last 6 candles) - (QQQ 5m return over last 6 candles)
- RS > 0 implies the ticker is stronger than the tape

## 9) Scoring model (deterministic)
We implement a momentum state machine:
- NO_MOMO, BUILDING, ACTIVE, PAUSE, FAILING, FAILED

Decision mapping (high-level):
- BUY: only when State=ACTIVE AND all Hard Gates pass
- HOLD: when BUILDING/PAUSE (or ACTIVE but gates fail)
- EXIT: when FAILING/FAILED (with confirmation logic)

### Hard Gates (must pass to BUY)
Examples (v1 core):
- Liquidity gate passes (see below)
- 15m structure intact
- “No chase” gate: distance from VWAP/EMA20 not more than 2 * ATR(14, 5m)
- Tape gate: avoid entries when Market RiskOff unless RS is strong enough

### Liquidity gates (v1)
If a ticker fails liquidity/volume thresholds:
- return IGNORE (or HOLD with “liquidity fail”), and do not recommend intraday entries

## 10) Entry / exit / risk outputs (what API must return)
Entry styles:
- Pullback entry preferred
- Breakout entry allowed only if not chasing (ATR-based)

Exit confirmation:
- “Confirmed failure” requires multiple signals (not volume alone)

Risk outputs:
- Suggested entry range (price band)
- Stop (ATR-based)
- Targets (ATR-based)
- Optional trailing stop logic + time-stop logic (if implemented in v1, otherwise stub)

## 11) API endpoints (v1)
- GET /health
- GET /score?ticker=TSLA
  Returns a compact object including:
  - data freshness + missing TFs
  - tape regime (RiskOff) + RS
  - state (NO_MOMO/BUILDING/ACTIVE/...)
  - signal (BUY/HOLD/EXIT/IGNORE)
  - entry range, stop, targets
  - confidence, suggested size
  - audit strings: which gates passed/failed, why

- GET /snapshot?ticker=TSLA
  Returns latest candles + indicators (compact, most recent N only)

## 12) Non-goals (v1)
- No order execution
- No portfolio tracking
- No multi-ticker scaling (comes right after v1 works end-to-end)
