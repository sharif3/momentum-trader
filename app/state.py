from app.candles.builder import CandleBuilder
from app.candles.store import CandleStore

# Global in-memory store for the running API process
store = CandleStore(max_history=500)

# Builder that writes into the store
builder = CandleBuilder(store)
