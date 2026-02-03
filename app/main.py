import asyncio

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import get_settings
from app.jobs.rest_refresher import rest_refresh_loop
from app.jobs.ws_ingest import ws_ingest_loop
from app.providers.loader import get_provider
from app.state import builder

settings = get_settings()
provider = get_provider()

app = FastAPI(title="Momentum Trader API", version="0.1.0")
app.include_router(api_router)


@app.on_event("startup")
async def _startup():
    # REST refresher (higher timeframes)
        # REST refresher (higher timeframes)
    # We refresh:
    # - the primary ticker (default_ticker)
    # - tape context tickers (SPY + QQQ) for market regime + relative strength
    symbols = [
        settings.default_ticker.upper(),
        "SPY.US",
        "QQQ.US",
    ]

    for sym in symbols:
        asyncio.create_task(rest_refresh_loop(sym))

    # WS ingest (builds 1m/5m candles from ticks)
    asyncio.create_task(
        ws_ingest_loop(
            provider=provider,
            candle_builder=builder,
            symbols=settings.ws_symbols,
        )
    )

@app.on_event("shutdown")
async def _shutdown():
    close = getattr(provider, "close", None)
    if callable(close):
        close()

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "provider_config": settings.provider,
        "provider_loaded": provider.__class__.__name__,
    }
