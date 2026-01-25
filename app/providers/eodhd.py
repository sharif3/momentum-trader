from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


class EodhdProvider(MarketDataProvider):
    """
    EODHD provider.

    Milestone 4 (REST):
    - intraday candles: 1m / 5m / 1h via /api/intraday/{symbol}
    - daily candles: 1d via /api/eod/{symbol}
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.api_token = settings.eodhd_api_token.strip()
        self.base_url = settings.eodhd_base_url.strip() or "https://eodhd.com"

    async def stream_ticks(self, symbols: List[str]) -> AsyncIterator[Dict]:
        raise NotImplementedError("EODHD WebSocket streaming not implemented yet")

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        if not self.api_token:
            raise ValueError("Missing EODHD_API_TOKEN in .env")

        tf = timeframe.lower().strip()

        if tf in {"1m", "5m", "15m", "1h", "4h"}:
            return self._fetch_intraday(symbol=symbol, interval=tf, limit=limit)

        if tf == "1d":
            return self._fetch_eod_daily(symbol=symbol, limit=limit)

        raise ValueError(f"Unsupported timeframe for EODHD REST: {timeframe}")

    def _fetch_intraday(self, symbol: str, interval: str, limit: int) -> List[Dict]:
        url = f"{self.base_url}/api/intraday/{symbol}"
        params: Dict[str, str] = {
            "api_token": self.api_token,
            "fmt": "json",
            "interval": interval,
        }

        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        out: List[Dict] = []
        for row in data[-limit:]:
            raw_dt = row["datetime"]

            # EODHD sometimes returns unix seconds, sometimes a "YYYY-MM-DD HH:MM:SS" string.
            if isinstance(raw_dt, (int, float)) or (
                isinstance(raw_dt, str) and raw_dt.isdigit()
            ):
                ts = datetime.fromtimestamp(int(raw_dt), tz=timezone.utc)
            else:
                # Example: "2025-12-16 19:30:00"
                ts = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )

            out.append(
                {
                    "ts": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                }
            )

        return out

    def _fetch_eod_daily(self, symbol: str, limit: int) -> List[Dict]:
        url = f"{self.base_url}/api/eod/{symbol}"
        params: Dict[str, str] = {
            "api_token": self.api_token,
            "fmt": "json",
            "period": "d",
        }

        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        out: List[Dict] = []
        for row in data[-limit:]:
            dt = datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)
            out.append(
                {
                    "ts": dt,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                }
            )

        return out
