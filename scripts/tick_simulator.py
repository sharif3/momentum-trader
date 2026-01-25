from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.candles.builder import CandleBuilder
from app.candles.store import CandleStore
from app.models.market import Tick


def run(symbol: str = "TSLA", seconds: int = 360) -> None:
    """
    Generates fake ticks for `seconds` seconds and feeds them into CandleBuilder.

    - We simulate 1 tick per second.
    - Price does a random walk (moves up/down a bit each tick).
    - CandleBuilder returns a list of candles that closed because of the tick.
      We print each closed candle (1m and sometimes 5m).
    """
    store = CandleStore(max_history=500)
    builder = CandleBuilder(store)

    # Start at the current minute boundary so candles look clean.
    ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    price = 100.0

    print(f"Simulating ticks for {symbol} for {seconds} seconds...\n")

    for _ in range(seconds):
        price += random.uniform(-0.2, 0.2)
        size = random.randint(1, 50)

        tick = Tick(symbol=symbol, ts=ts, price=round(price, 2), size=float(size))

        closed_list = builder.on_tick(tick)
        for closed in closed_list:
            print(
                f"[CLOSED {closed.timeframe}] {closed.symbol} "
                f"{closed.start_ts.isoformat()} -> "
                f"O={closed.o} H={closed.h} L={closed.l} C={closed.c} V={closed.v}"
            )

        ts += timedelta(seconds=1)

    hist_1m = store.get_history(symbol, "1m")
    hist_5m = store.get_history(symbol, "5m")

    print(f"\nDone.")
    print(f"Closed 1m candles stored: {len(hist_1m)}")
    print(f"Closed 5m candles stored: {len(hist_5m)}")


if __name__ == "__main__":
    run()
