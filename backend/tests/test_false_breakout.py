import unittest
from app.analyzer.false_breakout import detect_false_breakouts

class TestFalseBreakout(unittest.TestCase):
    def setUp(self):
        self.base_time = 1700000000

    def make_candle(self, idx, o, h, l, c, v=100.0):
        return {
            "time": self.base_time + idx * 300,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v)
        }

    def test_false_breakout_up_wick(self):
        """Single candle wick sweep above resistance and close below."""
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 101, 99, 100),
            self.make_candle(2, 100, 106, 99, 99.5),  # High 106 > 105, Close 99.5 < 105
            self.make_candle(3, 99.5, 100, 97, 98),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2, "strength_score": 75}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["type"], "bearish_sweep")
        self.assertEqual(fb["direction"], "SHORT")
        self.assertEqual(fb["subType"], "wick_rejection")
        self.assertEqual(fb["levelPrice"], 105.0)
        self.assertEqual(fb["sweepPrice"], 106.0)
        self.assertEqual(fb["breakoutTime"], candles[2]["time"])
        self.assertEqual(fb["confirmationTime"], candles[2]["time"])

    def test_false_breakout_up_two_candle(self):
        """Candle 1 breaks out and closes above 105. Candle 2 returns and closes below 105."""
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 101, 99, 100),
            self.make_candle(2, 101, 107, 101, 106),  # Close 106 > 105
            self.make_candle(3, 106, 106.5, 102, 103), # Returns and closes 103 < 105
            self.make_candle(4, 103, 103.5, 98, 99),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 3, "strength_score": 80}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["type"], "bearish_sweep")
        self.assertEqual(fb["direction"], "SHORT")
        self.assertEqual(fb["subType"], "two_candle_reversal")
        self.assertEqual(fb["levelPrice"], 105.0)
        self.assertEqual(fb["sweepPrice"], 107.0)
        self.assertEqual(fb["breakoutTime"], candles[2]["time"])
        self.assertEqual(fb["confirmationTime"], candles[3]["time"])

    def test_false_breakout_down_wick(self):
        """Single candle wick sweep below support and close above."""
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 101, 99, 100),
            self.make_candle(2, 100, 101, 92, 96), # Support 95 breached (low 92), close 96 > 95
            self.make_candle(3, 96, 98, 95.5, 97),
        ]
        levels = [{"price": 95.0, "type": "support", "touches": 2, "strength_score": 70}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["type"], "bullish_sweep")
        self.assertEqual(fb["direction"], "LONG")
        self.assertEqual(fb["subType"], "wick_rejection")
        self.assertEqual(fb["levelPrice"], 95.0)
        self.assertEqual(fb["sweepPrice"], 92.0)
        self.assertEqual(fb["confirmationTime"], candles[2]["time"])

    def test_false_breakout_down_two_candle(self):
        """Candle 1 closes below 95. Candle 2 returns and closes above 95."""
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 101, 99, 100),
            self.make_candle(2, 99, 99.5, 93, 94),   # Closes 94 < 95
            self.make_candle(3, 94, 98, 93.5, 97),   # Returns and closes 97 > 95
            self.make_candle(4, 97, 99, 96, 98),
        ]
        levels = [{"price": 95.0, "type": "support", "touches": 3, "strength_score": 85}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["type"], "bullish_sweep")
        self.assertEqual(fb["direction"], "LONG")
        self.assertEqual(fb["subType"], "two_candle_reversal")
        self.assertEqual(fb["levelPrice"], 95.0)
        self.assertEqual(fb["sweepPrice"], 93.0)
        self.assertEqual(fb["breakoutTime"], candles[2]["time"])
        self.assertEqual(fb["confirmationTime"], candles[3]["time"])

    def test_true_breakout_does_not_trigger_false_breakout(self):
        """True breakout continues moving away, no return."""
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 106, 99, 106),
            self.make_candle(2, 106, 110, 105, 109),
            self.make_candle(3, 109, 114, 108, 112),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 0)

if __name__ == "__main__":
    unittest.main()
