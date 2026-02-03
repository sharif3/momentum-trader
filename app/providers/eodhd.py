from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
import websockets

log = logging.getLogger("eodhd_provider")


class EodhdProvider:
    """
    EODHD Provider (REST + WS).

    REST:
    - fetch candles for 15m/1h/4h/1d (and intraday)

    WS:
    - live trade ticks for 1m/5m candle building
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

    def close(self) -> None:
        self._client.close()
    
    def _build_ws_url(self) -> str:
        raw = (os.getenv("EODHD_WS_URL") or "wss://ws.eodhistoricaldata.com/ws/us").strip()
        if "api_token=" in raw:
            return raw
        sep = "&" if "?" in raw else "?"
        return f"{raw}{sep}api_token={self.api_token}"

    def _build_ws_symbol_map(self, symbols: list[str]) -> tuple[list[str], dict[str, str]]:
        wire_symbols: list[str] = []
        symbol_map: dict[str, str] = {}

        for s in symbols:
            s = s.strip().upper()
            if not s:
                continue
            wire = s[:-3] if s.endswith(".US") else s
            wire_symbols.append(wire)
            symbol_map[wire] = s

        return wire_symbols, symbol_map

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
        WS tick stream (real).

        Connects to EODHD WS, subscribes to symbols, and yields ticks:
          {"symbol": "...", "price": ..., "size": ..., "t_ms": ...}
        """
        wire_symbols, symbol_map = self._build_ws_symbol_map(symbols)

        if not wire_symbols:
            log.warning("EODHD WS: no symbols provided")
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield {}

        ws_url = self._build_ws_url()
        backoff = 1.0

        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    # Wait for auth message first (EODHD sends {"status_code":200,...})
                    try:
                        first = await asyncio.wait_for(ws.recv(), timeout=5)
                        try:
                            auth = json.loads(first)
                            if isinstance(auth, dict) and auth.get("status_code") == 200:
                                log.warning("EODHD WS authorized")
                            else:
                                log.warning("EODHD WS first msg=%s", auth)
                        except Exception:
                            log.warning("EODHD WS first msg (raw)=%s", first)
                    except asyncio.TimeoutError:
                        log.warning("EODHD WS auth message timeout (continuing)")

                    sub = {"action": "subscribe", "symbols": ",".join(wire_symbols)}
                    await ws.send(json.dumps(sub))

                    log.warning("EODHD WS subscribed symbols=%s", wire_symbols)
                    backoff = 1.0
                    first_tick_logged = False
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue

                        if not isinstance(data, dict):
                            continue

                        s = data.get("s")
                        p = data.get("p")
                        v = data.get("v")
                        t = data.get("t")

                        if s is None or p is None or v is None or t is None:
                            continue

                        s_up = str(s).upper()
                        symbol = symbol_map.get(s_up, s_up)
                        if ".US" not in symbol and "." not in symbol:
                            symbol = f"{symbol}.US"

                        yield {
                            "symbol": symbol,
                            "price": float(p),
                            "size": float(v),
                            "t_ms": int(t),
                        }
                        if not first_tick_logged:
                            log.warning(
                                "EODHD WS first tick symbol=%s price=%s size=%s t_ms=%s",
                                symbol, p, v, t
                            )
                            first_tick_logged = True

            except Exception as e:
                log.warning("EODHD WS error: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

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
            log.warning(
                "Unexpected intraday payload type symbol=%s interval=%s type=%s",
                symbol,
                interval,
                type(data),
            )
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
