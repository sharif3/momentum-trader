import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Loads variables from a local .env file into environment variables (dev only).
# In production, you'd typically set env vars via the hosting environment instead.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    Settings = your app's configuration.
    These values come from environment variables so we can change behavior
    without changing code (e.g., swap data providers).
    """
    app_env: str
    log_level: str
    provider: str


def get_settings() -> Settings:
    """
    Reads env vars and returns a Settings object.
    Provides safe defaults so the app can run even before you set anything.
    """
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        provider=os.getenv("PROVIDER", "EODHD"),
    )
