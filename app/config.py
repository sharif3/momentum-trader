import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Loads variables from a local .env file into environment variables (dev only).
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    App configuration loaded from environment variables.
    """
    app_env: str
    log_level: str
    provider: str
    default_ticker: str

    # EODHD (provider-specific, but safe to keep here as config)
    eodhd_base_url: str
    eodhd_api_token: str


def get_settings() -> Settings:
    """
    Reads env vars and returns a Settings object.
    """
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        provider=os.getenv("PROVIDER", "EODHD"),
        eodhd_base_url=os.getenv("EODHD_BASE_URL", "https://eodhd.com"),
        eodhd_api_token=os.getenv("EODHD_API_TOKEN", ""),
        default_ticker=os.getenv("DEFAULT_TICKER", "TSLA.US"),
    )
