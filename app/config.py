# app/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Loads variables from a local .env file into environment variables (dev only).
load_dotenv()


@dataclass(frozen=True)
class Settings:
    # App config
    app_env: str
    log_level: str
    provider: str
    default_ticker: str

    # Provider config (EODHD)
    eodhd_base_url: str
    eodhd_api_token: str
    eodhd_ws_url: str
    ws_symbols: list[str]


def get_settings() -> Settings:
    """
    Reads env vars and returns a Settings object.
    """
    token = os.getenv("EODHD_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("EODHD_API_TOKEN is missing. Add it to .env")

    ws_symbols = [s.strip() for s in os.getenv("WS_SYMBOLS", "TSLA").split(",") if s.strip()]

    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        provider=os.getenv("PROVIDER", "EODHD"),
        default_ticker=os.getenv("DEFAULT_TICKER", "TSLA.US"),
        eodhd_base_url=os.getenv("EODHD_BASE_URL", "https://eodhd.com"),
        eodhd_api_token=token,
        eodhd_ws_url=os.getenv("EODHD_WS_URL", "wss://ws.eodhistoricaldata.com/ws/us"),
        ws_symbols=ws_symbols,
    )
