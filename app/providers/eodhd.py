from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

import httpx
import websockets

from app.config import get_settings
from app.providers.base import MarketDataProvider


class EodhdProvider(MarketDataProvider):
    """
    EODHD provider.

    Milestone 4 (REST):
    - intraday candles: 1m / 5m / 15m / 1h / 4h via /api/intraday/{symbol}
    - daily candles: 1d via /api/eod/{symbol}
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.api_token = settings.eodhd_api_token.strip()
        self.base_url = settings.eodhd_base_url.strip() or "https://eodhd.com"
        self.ws_url = settings.eodhd_ws_url.strip()

    async def stream_ticks(self, symbols: List[str]) -> AsyncIterator[Dict]:
        """
        Connects to EODHD WebSocket and yields raw tick dicts.

        Yields only messages that look like trade ticks:
          - s: symbol
          - p: price
          - t: epoch milliseconds
          - v: size (optional)
        """
        if not self.api_token:
            raise ValueError("Missing EODHD_API_TOKEN in .env")

        url = f"{self.ws_url}?api_token={self.api_token}"
        sub_msg = {"action": "subscribe", "symbols": ",".join(symbols)}

        backoff = 1
        while True:
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20
                ) as ws:
                    await ws.send(json.dumps(sub_msg))

                    async for raw in ws:
                        data = json.loads(raw)

                        # Ignore non-tick messages (authorized, heartbeats, etc.)
                        if not all(k in data for k in ("s", "p", "t")):
                            continue

                        # Normalize into a consistent dict shape for the rest of the app
                        yield {
                            "symbol": str(data["s"]),
                            "price": float(data["p"]),
                            "size": float(data.get("v") or 0.0),
                            "t_ms": float(data["t"]),
                        }

            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

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
