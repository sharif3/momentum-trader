import unittest

from app.candles.store import CandleStore
from app.models.market_context import MarketContext
from app.scoring.engine import score_symbol


class TestScoringEngine(unittest.TestCase):
    def test_missing_required_timeframes(self):
        store = CandleStore()
        mc = MarketContext(regime="UNKNOWN", risk_off=False, rs_30m=None, audit=[])

        result = score_symbol(
            symbol="TSLA.US",
            store=store,
            market_context=mc,
            missing_timeframes=["5m"],
            ema_5m={},
            ema_15m={},
            atr_5m={},
            vwap_5m={},
        )

        self.assertEqual(result["signal"], "HOLD")
        self.assertEqual(result["state"], "NO_MOMO")
        self.assertTrue(
            any("missing required timeframe(s): 5m" in s for s in result["audit"])
        )
