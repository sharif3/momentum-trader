# Architecture

## 1) System overview (plain English)
Think of the app as a pipeline:

Provider (WS/REST) -> Candle Builder -> Candle Store -> Indicators -> Scoring -> API

Each stage is separate so we can:
- swap data providers
- test components in isolation
- scale from 1 ticker to many

## 2) Core design principles
- Provider-agnostic: core logic never calls EODHD directly
- Deterministic: same inputs -> same outputs
- Observable: every score includes “why” (audit trail)
- Safe defaults: if data missing/stale -> HOLD (or IGNORE), never BUY

## 3) Modules (v1 target structure)

### app/main.py
- FastAPI app creation
- includes routes

### app/config.py
- Loads environment variables (from OS env and .env locally)
- Example config: provider name, API base URLs, log level

### app/providers/base.py
Defines provider interfaces (contracts), e.g.:
- get_candles_rest(symbol, timeframe, start, end) -> candles
- connect_ticks_ws(symbols) -> async tick stream
This is the “adapter point” for swapping providers.

### app/providers/eodhd.py
Concrete implementation of the base provider interface for EODHD:
- REST candle fetch
- WebSocket tick subscription

### app/models/*
Data models (simple Python classes / pydantic models):
- Tick (time, price, size, exchange, etc.)
- Candle (timeframe, start_ts, o/h/l/c, volume, session_tag)
- IndicatorSet (ema9/20/50/200, vwap, atr, obv_slope, etc.)
- ScoreResult (signal/state/confidence/size/levels/audit)

### app/candles/builder.py
- Converts ticks -> 1m candles
- Aggregates 1m -> 5m
- Optionally aggregates 1m -> forming 15m (current bar only)

### app/candles/store.py
- In-memory store (dict keyed by symbol+timeframe)
- Keeps latest N candles per timeframe
- Tracks freshness/staleness and gap detection

### app/indicators/engine.py
- Computes indicators for each timeframe from candles
- Writes IndicatorSet back into store or returns per request

### app/market_context/engine.py
- Computes tape context (SPY/QQQ risk regime)
- Computes relative strength vs QQQ

### app/scoring/engine.py
- Implements state machine + hard gates + decision mapping
- Produces ScoreResult with audit trail (gates pass/fail reasons)

### app/api/routes.py
- GET /health
- GET /score?ticker=
- GET /snapshot?ticker=

## 4) Runtime processes (how it runs)
We’ll run two loops (v1, single process):
1) WebSocket loop: streams ticks and continuously updates 1m/5m candles
2) REST refresh loop (timer): periodically refreshes 15m/1h/4h/1d closed candles

FastAPI serves requests at any time by reading from the in-memory store.

## 5) Data freshness rules (important)
- If 5m or 15m are stale/missing -> HOLD and report missing TFs
- 1m/5m are considered “live” when fed by WS
- 15m current bar may be “forming” from WS (clearly labeled)
- Closed 15m/1h/4h/1d should come from REST and be timestamp-validated

## 6) Extensibility (provider swap)
To swap provider:
- implement app/providers/<provider>.py matching base interface
- set PROVIDER=<name> in .env
No other code changes.
