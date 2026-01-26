import os
import sys

# Add repo root to Python import path so `import app...` works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
from dotenv import load_dotenv

load_dotenv()

from app.providers.eodhd import EodhdProvider

async def main():
    p = EodhdProvider()
    symbols = ["TSLA"]

    got = 0
    async for tick in p.stream_ticks(symbols):
        print("TICK:", tick)
        got += 1
        if got >= 3:
            break

    if got == 0:
        print("No ticks received (likely market closed). Connection/auth still may be OK.")

if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=8))
    except asyncio.TimeoutError:
        print("Timed out waiting for ticks (likely market closed).")
