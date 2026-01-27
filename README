# Momentum Trader (v1)

Local backend service pipeline for deterministic momentum scoring.

## What it does
- Ingests ticks (WS) for 1m/5m candles
- Refreshes higher timeframes (15m/1h/4h/1d) via REST
- Computes indicators per timeframe
- Builds tape context (risk regime + relative strength)
- Scores signals with a deterministic state machine
- Exposes REST endpoints for snapshots and scores

## Pipeline
Provider (WS/REST) -> Candle Builder -> Candle Store -> Indicators -> Tape Context -> Scoring -> API

## Quick start
1) Create a `.env` file (see Configuration below).
2) Create and activate a virtualenv, then install deps:
