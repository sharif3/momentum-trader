from fastapi import FastAPI

import asyncio
from app.jobs.rest_refresher import rest_refresh_loop

from app.api.routes import router as api_router
from app.config import get_settings
from app.providers.loader import get_provider

settings = get_settings()
provider = get_provider()

app = FastAPI(title="Momentum Trader API", version="0.1.0")

app.include_router(api_router)

@app.on_event("startup")
async def _startup():
    # start background REST refresher for default ticker
    asyncio.create_task(rest_refresh_loop(settings.default_ticker.upper()))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "provider_config": settings.provider,
        "provider_loaded": provider.__class__.__name__,
    }
