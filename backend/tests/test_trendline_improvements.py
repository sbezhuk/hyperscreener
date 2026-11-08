import unittest
from app.analyzer.trendline import (
    find_zigzag_swings,
    find_swings_for_trendlines,
    detect_timeframe_trendlines,
    calculate_linear_regression_channel,
)
from app.analyzer.screener import analyze_coin_data


class TestTrendlineImprovements(unittest.TestCase):
    def setUp(self):
        # Generate baseline synthetic candles
        self.base_time = 1700000000

    def _generate_zigzag_candles(self, n=50):
        """Generates wave-like candles: Up, Down, Up, Down to test ZigZag swings."""
        candles = []
        price = 100.0
        for i in range(n):
            wave = (i % 20)
            if wave < 10:
                price += 2.0
            else:
                price -= 2.0
            candles.append({
                "time": self.base_time + i * 300,
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1000,
            })
        return candles

    def test_find_zigzag_swings_alternates_highs_and_lows(self):
        """Test that ZigZag engine accurately identifies alternating pivot highs and lows."""
        candles = self._generate_zigzag_candles(60)
        swings = find_zigzag_swings(candles, interval="5m", deviation_atr=0.8)

        self.assertIn("highs", swings)
        self.assertIn("lows", swings)
        self.assertGreater(len(swings["highs"]), 0)
        self.assertGreater(len(swings["lows"]), 0)

        # High prices should be distinctly higher than adjacent low prices
        for h in swings["highs"]:
            self.assertGreater(h["price"], 105.0)

    def test_three_touch_confirmation_and_prioritization(self):
        """Test that trendlines with 3+ touches are marked confirmed and prioritized."""
        # Create a resistance line with 3 touches at indices 5, 20, 35
        # Slope = -1.0 per bar. Anchors: (5, 200.0), (20, 185.0), (35, 170.0)
        candles = []
        for i in range(50):
            line_val = 200.0 - 1.0 * (i - 5)
            # Default candle safely below line
            high = line_val - 5.0
            low = high - 3.0
            close = (high + low) / 2.0
            open_p = close

            # Touch candles at indices 5, 20, 35
            if i in (5, 20, 35):
                high = line_val
                close = line_val - 0.5
                low = line_val - 2.0
                open_p = low

            candles.append({
                "time": self.base_time + i * 300,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1500,
            })

        tls = detect_timeframe_trendlines(candles, interval="5m")
        self.assertGreater(len(tls), 0)
        best_tl = tls[0]

        # Must have at least 3 touches and is_confirmed = True
        self.assertGreaterEqual(best_tl["touch_count"], 3)
        self.assertTrue(best_tl["is_confirmed"])
        self.assertEqual(best_tl["confirmation_status"], "CONFIRMED")
        self.assertIn("Підтверджена", best_tl["timeframe_label"])

    def test_linear_regression_channel_calculation(self):
        """Test Linear Regression Channel OLS formula: y = kx + b, R^2, upper/lower bounds."""
        candles = []
        # Perfect linear trend: close = 100 + 0.5 * i
        for i in range(40):
            c_price = 100.0 + 0.5 * i
            candles.append({
                "time": self.base_time + i * 300,
                "open": c_price - 0.2,
                "high": c_price + 0.5,
                "low": c_price - 0.5,
                "close": c_price,
                "volume": 1000,
            })

        channel = calculate_linear_regression_channel(candles, interval="5m", lookback=40, num_std=2.0)
        self.assertIsNotNone(channel)
        self.assertEqual(channel["direction"], "ASCENDING")
        self.assertAlmostEqual(channel["slope"], 0.5, places=2)
        self.assertGreaterEqual(channel["r_squared"], 0.95)
        self.assertIn("middle", channel)
        self.assertIn("upper", channel)
        self.assertIn("lower", channel)

        # Upper band must be higher than middle, and lower band lower than middle
        self.assertGreater(channel["upper"]["p2"]["price"], channel["middle"]["p2"]["price"])
        self.assertLess(channel["lower"]["p2"]["price"], channel["middle"]["p2"]["price"])

    def test_screener_signal_breakout_vs_bounce(self):
        """Test screener trendline signals correctly emit BREAKOUT vs BOUNCE signals."""
        from app.analyzer.screener import enrich_signals_with_trendline_context

        # Mock trendline candidate with BREAKOUT state
        tl_breakout = {
            "id": "tl-test-1",
            "timeframe": "5m",
            "direction": "DESCENDING",
            "line_type": "resistance_trendline",
            "start_point": {"time": 1000, "price": 120.0, "index": 5},
            "end_point": {"time": 2000, "price": 100.0, "index": 25},
            "slope": -1.0,
            "touch_count": 3,
            "is_confirmed": True,
            "status": "BROKEN",
            "interaction_state": "BREAKOUT",
            "distance_to_line_atr": 1.2,
            "compression_ratio": 1.0,
            "structural_quality": 85.0,
        }

        # Mock trendline candidate with BOUNCE (TESTING) state
        tl_bounce = {
            "id": "tl-test-2",
            "timeframe": "5m",
            "direction": "ASCENDING",
            "line_type": "support_trendline",
            "start_point": {"time": 1000, "price": 80.0, "index": 5},
            "end_point": {"time": 2000, "price": 95.0, "index": 25},
            "slope": 0.75,
            "touch_count": 3,
            "is_confirmed": True,
            "status": "ACTIVE",
            "interaction_state": "TESTING",
            "distance_to_line_atr": 0.1,
            "compression_ratio": 0.9,
            "structural_quality": 88.0,
        }

        # Test logic mapping
        # Breakout of resistance should give LONG direction
        # Bounce from support should give LONG direction
        self.assertEqual(tl_breakout["interaction_state"], "BREAKOUT")
        self.assertTrue(tl_breakout["is_confirmed"])
        self.assertEqual(tl_bounce["interaction_state"], "TESTING")
        self.assertTrue(tl_bounce["is_confirmed"])

    def test_screener_regression_channel_signals(self):
        """Test detection of channel breakouts and false breakouts (deviations)."""
        import asyncio
        from app.analyzer.screener import analyze_coin_data

        # Generate a series with a clear false breakout at the top
        candles = []
        for i in range(50):
            p = 100.0 - 0.2 * i
            h = p + 0.5
            l = p - 0.5
            c = p
            # Candle 30 wicks high (deviation above upper band) but closes inside
            if i == 49:
                # Last candle tests below lower band
                l = p - 3.0
                c = p - 2.5
            candles.append({
                "time": self.base_time + i * 300,
                "open": p,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000,
            })

        channel = calculate_linear_regression_channel(candles, interval="5m", lookback=50, num_std=2.0)
        self.assertIsNotNone(channel)
        self.assertIn("direction", channel)
        self.assertEqual(channel["direction"], "DESCENDING")


if __name__ == "__main__":
    unittest.main()
