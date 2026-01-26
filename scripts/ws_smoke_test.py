import asyncio
import json
import os
from datetime import datetime, timezone

import websockets
from dotenv import load_dotenv

load_dotenv()

# Reads from your .env (already loaded by your app config, but this script uses OS env directly)
API_TOKEN = os.getenv("EODHD_API_TOKEN")
WS_URL = os.getenv("EODHD_WS_URL", "wss://ws.eodhistoricaldata.com/ws/us")
SYMBOLS = os.getenv("WS_SYMBOLS", "TSLA")


async def main():
    if not API_TOKEN:
        raise RuntimeError("EODHD_API_TOKEN missing. Put it in .env")

    # EODHD expects api_token on the URL query string
    url = f"{WS_URL}?api_token={API_TOKEN}"

    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        # Subscribe message format for EODHD
        await ws.send(json.dumps({"action": "subscribe", "symbols": SYMBOLS}))
        print("Subscribed to:", SYMBOLS)

        # Print the next 20 messages
        for i in range(20):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                print(i + 1, "NO_MESSAGE_IN_5S (market likely closed)")
                break

            data = json.loads(raw)

            # If it's not a trade tick, print the whole message and continue
            if not all(k in data for k in ("s", "p", "t")):
                print(i + 1, "NON_TICK:", data)
                continue

            ts = datetime.fromtimestamp(float(data["t"]) / 1000.0, tz=timezone.utc)
            print(i + 1, "TICK:", data["s"], data["p"], data.get("v"), ts)


if __name__ == "__main__":
    asyncio.run(main())
