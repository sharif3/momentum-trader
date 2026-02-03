# TODO

## Milestone 1: Scaffold ✅
- FastAPI runs locally
- /health works
- repo pushed

## Milestone 2: Provider-agnostic foundation
- Create provider interface (base.py)
- Add EODHD provider implementation (eodhd.py) with stub methods first
- Add config loader (config.py) + .env.example keys (no real key committed)
- Add data models: Tick, Candle, ScoreResult

## Milestone 3: Candle pipeline (real-time intraday)
- Implement 1m candle builder from ticks
- Implement 5m aggregation from 1m
- Add in-memory candle store with “latest N” retention
- Add staleness/gap detection
- Add a tick simulator (so we can test without WS)

## Milestone 4: REST candle refresh (higher TF)
- Implement REST fetch for 15m/1h/4h/1d candles (closed bars)
- Add refresh scheduler (simple asyncio task)
- Implement “forming 15m” from 1m (optional but recommended)

## Milestone 5: Indicators
- Implement EMA set (9/20/50/200) per TF as defined
- Implement VWAP (RTH) + fallback anchor
- Implement PriorHigh20/PriorLow20 (5m/15m)
- Implement ATR(14) (5m/15m)
- Implement OBV slope (5m/15m)
- Implement RelVol (basic first, session split later)

## Milestone 6: Tape context
- Add SPY + QQQ candles (5m/15m)
- Implement Market RiskOff
- Implement RS_30m vs QQQ

## Milestone 7: Scoring engine ✅
- Implement momentum state machine
- Implement hard gates
- Implement decision mapping (BUY/HOLD/EXIT/IGNORE)
- Return audit trail (why gates failed/passed)

## Milestone 8: API endpoints ✅
- GET /score?ticker=
- GET /snapshot?ticker=
- Include freshness + missing TFs + audit in response
- EXT thin-volume gate added (relvol20)
- Pending live test: verify gap_check during market hours (5m/15m data present)
- Runtime reliability fixes (pending):
  - Drop partial REST candles (15m/1h/1d) before storing
  - Guard WS ingest against malformed tick messages
  - Close HTTP client on shutdown



## Milestone 9: WebSocket ticks (real-time intraday) ✅
- Implement real provider WS stream_ticks (connect/auth/subscribe)
- Parse trade messages into {symbol, price, size, t_ms}
- Feed ticks into CandleBuilder to populate 1m/5m
- Add SPY/QQQ to WS symbols config (or document WS_SYMBOLS usage)
- Add reconnect/backoff + logging
- Add smoke test instructions for live ticks

## Milestone 10: GPT Actions ✅
- Define OpenAPI schema for endpoints
- Wire GPT Action calls to /score and /snapshot

## After v1 works end-to-end
- Multi-ticker support
- Persistent store (Redis) if needed
- Better session handling (RTH/EXT) + robust RelVol
- Tests: unit tests for candle builder, indicator engine, scoring rules
