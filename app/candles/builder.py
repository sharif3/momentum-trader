from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.candles.store import CandleStore
from app.models.market import Candle, Tick


def floor_to_minute(ts: datetime) -> datetime:
    """Round timestamp down to start of its minute (UTC)."""
    ts = ts.astimezone(timezone.utc)
    return ts.replace(second=0, microsecond=0)


def floor_to_5min(ts: datetime) -> datetime:
    """Round timestamp down to start of its 5-minute window (UTC)."""
    ts = floor_to_minute(ts)
    minute = (ts.minute // 5) * 5
    return ts.replace(minute=minute)


class CandleBuilder:
    """
    Builds candles from ticks.

    v1 approach:
    - ticks -> 1m candles (real-time)
    - closed 1m candles -> 5m candles (aggregation)
    """

    def __init__(self, store: CandleStore):
        self.store = store

    def on_tick(self, tick: Tick) -> list[Candle]:
        """
        Process one tick.
        Returns candles that closed because of this tick (usually none).
        """
        closed: list[Candle] = []

        closed_1m = self._on_tick_1m(tick)
        if closed_1m is not None:
            closed.append(closed_1m)

            closed_5m = self._on_close_1m_update_5m(closed_1m)
            if closed_5m is not None:
                closed.append(closed_5m)

        return closed

    def _on_tick_1m(self, tick: Tick) -> Candle | None:
        """Convert ticks into 1m candles. Returns a closed 1m candle when minute flips."""
        symbol = tick.symbol
        timeframe = "1m"

        start_ts = floor_to_minute(tick.ts)
        end_ts = start_ts + timedelta(minutes=1)

        current = self.store.get_current(symbol, timeframe)

        # Start a new 1m candle if none exists.
        if current is None:
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                o=tick.price,
                h=tick.price,
                l=tick.price,
                c=tick.price,
                v=tick.size,
            )
            self.store.set_current(candle)
            return None
            
        # Drop out-of-order ticks (older than current candle start)
        if current is not None and tick.ts < current.start_ts:
            return None

        # Still inside current 1m window -> update.
        if tick.ts < current.end_ts:
            current.update(price=tick.price, size=tick.size)
            self.store.touch(symbol, timeframe)
            return None

        # Minute rolled -> close old 1m and start new 1m.
        closed = self.store.close_current(symbol, timeframe)

        new_candle = Candle(
            symbol=symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            o=tick.price,
            h=tick.price,
            l=tick.price,
            c=tick.price,
            v=tick.size,
        )
        self.store.set_current(new_candle)

        return closed

    def _on_close_1m_update_5m(self, closed_1m: Candle) -> Candle | None:
        """
        Update (or create) the current 5m candle using a closed 1m candle.
        Returns a closed 5m candle when a 5m window completes.
        """
        symbol = closed_1m.symbol
        timeframe = "5m"

        start_5m = floor_to_5min(closed_1m.start_ts)
        end_5m = start_5m + timedelta(minutes=5)

        current_5m = self.store.get_current(symbol, timeframe)

        # Need a new 5m candle if none exists OR we've moved into a new 5m window.
        if current_5m is None or start_5m >= current_5m.end_ts:
            closed_5m = None

            # If we had an old 5m candle and moved past it, close it.
            if current_5m is not None and start_5m >= current_5m.end_ts:
                closed_5m = self.store.close_current(symbol, timeframe)

            new_5m = Candle(
                symbol=symbol,
                timeframe=timeframe,
                start_ts=start_5m,
                end_ts=end_5m,
                o=closed_1m.o,
                h=closed_1m.h,
                l=closed_1m.l,
                c=closed_1m.c,
                v=closed_1m.v,
            )
            self.store.set_current(new_5m)

            return closed_5m

        # Same 5m window -> update from the closed 1m bar.
        current_5m.h = max(current_5m.h, closed_1m.h)
        current_5m.l = min(current_5m.l, closed_1m.l)
        current_5m.c = closed_1m.c
        current_5m.v += closed_1m.v
        self.store.touch(symbol, timeframe)

        return None
