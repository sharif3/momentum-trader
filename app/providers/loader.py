from app.config import get_settings
from app.providers.base import MarketDataProvider
from app.providers.eodhd import EodhdProvider


def get_provider() -> MarketDataProvider:
    """
    Provider loader / factory.

    Reads PROVIDER from config and returns an instance of the selected provider.
    This is the single place that knows about concrete providers.
    """
    settings = get_settings()
    provider_name = settings.provider.strip().upper()

    if provider_name == "EODHD":
        return EodhdProvider()

    raise ValueError(f"Unknown PROVIDER='{settings.provider}'. Expected: EODHD")
