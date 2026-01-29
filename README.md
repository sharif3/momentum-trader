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

## Endpoints

## OpenAPI (for GPT Actions)
The OpenAPI schema is in:
- `openapi.yaml`

Use this file when creating a GPT Action.

## GPT Actions (local dev via ngrok)
GPT Actions run on OpenAI servers, so they cannot reach localhost directly.
Use ngrok to create a public HTTPS URL.

Workflow:
1) Start your API:

