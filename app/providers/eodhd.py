from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger("eodhd_provider")


class EodhdProvider:
    """
    EODHD Provider (REST + WS stub for now).

    Why this file exists:
    - Your app currently runs BOTH:
        - REST refresh loop (higher timeframes)
        - WS ingest loop (ticks)
      Even if WS isn't implemented yet, we must NOT crash at startup.

    What this provider guarantees:
    - REST candle fetch works against the correct EODHD base URL (.../api).
    - Bad/partial rows (None fields) are skipped (no float(None) crashes).
    - stream_ticks() exists (stub) so ws_ingest_loop doesn't error.
    """

    def __init__(self) -> None:
        # Accept either env var name
        self.api_token = os.getenv("EODHD_API_TOKEN") or os.getenv("EODHD_API_KEY")
        if not self.api_token:
            raise RuntimeError("Missing EODHD API token. Set EODHD_API_TOKEN in your .env.")

        # IMPORTANT: EODHD REST endpoints live under https://eodhd.com/api
        raw_base = (os.getenv("EODHD_BASE_URL") or "https://eodhd.com/api").rstrip("/")

        # If user set EODHD_BASE_URL=https://eodhd.com, force /api
        if raw_base == "https://eodhd.com":
            raw_base = "https://eodhd.com/api"
        if raw_base.endswith("eodhd.com") and not raw_base.endswith("/api"):
            raw_base = raw_base + "/api"

        self.base_url = raw_base

        timeout_s = float(os.getenv("EODHD_TIMEOUT_SECONDS", "20"))
        self._client = httpx.Client(timeout=timeout_s)

    # -------------------------
    # Public interface used by the app
    # -------------------------
    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 300) -> list[dict]:
        """
        Returns candles as list[dict]:
          {"ts": datetime, "open": float, "high": float, "low": float, "close": float, "volume": float}

        timeframe in this repo: "15m", "1h", "4h", "1d" (and later "1m", "5m").
        """
        tf = (timeframe or "").lower().strip()

        if tf in ("1d", "d", "day", "daily"):
            return self._fetch_daily(symbol, limit=limit)

        return self._fetch_intraday(symbol, interval=tf, limit=limit)

    async def stream_ticks(self, symbols: list[str]) -> AsyncIterator[dict]:
        """
        WS tick stream (stub).

        Your app starts ws_ingest_loop() at startup and expects this method.
        We keep it alive (no crash), but we DON'T emit ticks yet.
        We'll implement real WS later when we do the WS milestone.
        """
        log.warning("EODHD stream_ticks() stub active. WS ticks not implemented yet. symbols=%s", symbols)
        while True:
            await asyncio.sleep(3600)
            if False:  # keeps this an async generator
                yield {}

    # -------------------------
    # REST: intraday
    # -------------------------
    def _fetch_intraday(self, symbol: str, interval: str, limit: int) -> list[dict]:
        """
        EODHD intraday endpoint:
          GET {base_url}/intraday/{symbol}?api_token=...&interval=15m&fmt=json
        """
        url = f"{self.base_url}/intraday/{symbol}"
        params = {
            "api_token": self.api_token,
            "fmt": "json",
            "interval": interval,
        }
        if limit:
            params["limit"] = str(limit)

        resp = self._client.get(url, params=params)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            log.warning("Unexpected intraday payload type symbol=%s interval=%s type=%s", symbol, interval, type(data))
            return []

        out: list[dict] = []
        for row in data:
            if not isinstance(row, dict):
                continue

            # Field names can vary; handle common variants
            ts_raw = row.get("datetime") or row.get("timestamp") or row.get("date")
            o = row.get("open")
            h = row.get("high")
            l = row.get("low")
            c = row.get("close")
            v = row.get("volume")

            # Skip partial/invalid rows (prevents float(None) crashes)
            if ts_raw is None or o is None or h is None or l is None or c is None or v is None:
                continue

            try:
                out.append(
                    {
                        "ts": self._parse_ts(ts_raw),
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v),
                    }
                )
            except Exception:
                continue

        out.sort(key=lambda x: x["ts"])
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    # -------------------------
    # REST: daily
    # -------------------------
    def _fetch_daily(self, symbol: str, limit: int) -> list[dict]:
        """
        EODHD daily endpoint:
          GET {base_url}/eod/{symbol}?api_token=...&fmt=json
        """
        url = f"{self.base_url}/eod/{symbol}"
        params = {"api_token": self.api_token, "fmt": "json"}

        resp = self._client.get(url, params=params)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            log.warning("Unexpected daily payload type symbol=%s type=%s", symbol, type(data))
            return []

        out: list[dict] = []
        for row in data:
            if not isinstance(row, dict):
                continue

            ts_raw = row.get("date") or row.get("datetime") or row.get("timestamp")
            o = row.get("open")
            h = row.get("high")
            l = row.get("low")
            c = row.get("close")
            v = row.get("volume")

            if ts_raw is None or o is None or h is None or l is None or c is None or v is None:
                continue

            try:
                out.append(
                    {
                        "ts": self._parse_ts(ts_raw),
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v),
                    }
                )
            except Exception:
                continue

        out.sort(key=lambda x: x["ts"])
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    # -------------------------
    # Timestamp parsing
    # -------------------------
    def _parse_ts(self, ts_raw: Any) -> datetime:
        """
        Converts timestamp to datetime (UTC).
        Handles:
          - epoch seconds/millis
          - "YYYY-MM-DD"
          - "YYYY-MM-DD HH:MM:SS"
          - ISO strings
        """
        if isinstance(ts_raw, (int, float)):
            if ts_raw > 1_000_000_000_000:  # millis
                return datetime.fromtimestamp(ts_raw / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(ts_raw, tz=timezone.utc)

        s = str(ts_raw).strip()
        s = s.replace(" ", "T")

        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
