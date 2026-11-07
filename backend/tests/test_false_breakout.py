import unittest
import time
from app.analyzer.false_breakout import (
    detect_false_breakouts,
    evaluate_false_breakout_oi,
    FalseBreakoutOIConfig,
    DEFAULT_OI_CONFIG
)
from app.analyzer.oi_tracker import OITracker, OISnapshot


class TestFalseBreakout(unittest.TestCase):
    def setUp(self):
        self.base_time = 1700000000

    def make_candle(self, idx, o, h, l, c, v=100.0, oi=None):
        candle = {
            "time": self.base_time + idx * 300,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v)
        }
        if oi is not None:
            candle["open_interest"] = float(oi)
        return candle

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

    # =========================================================================
    # NEW SPECIFICATION TEST SUITE: OPEN INTEREST (OI) CONFIRMATION FILTER
    # =========================================================================

    def test_scenario_1_breakout_returns_oi_decreases_confirmed(self):
        """
        Scenario 1: Price breaks level, returns back, OI decreases -> Signal is CONFIRMED.
        OI drops from 1000.0 before breakout to 980.0 (-2.0%), which exceeds min_oi_drop_pct (0.25%).
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=980.0),  # Pierces 105, returns below with OI drop
            self.make_candle(3, 99.5, 100, 97, 98, oi=978.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "CONFIRMED")
        self.assertTrue(fb["oiConfirmed"])
        self.assertEqual(fb["statusLabel"], "Підтверджений хибний пробій")
        self.assertAlmostEqual(fb["oiDeltaPct"], -2.0, places=2)
        self.assertIn("Підтверджений", fb["formation"])
        self.assertIn("скорочення OI", fb["desc"])

    def test_scenario_2_breakout_returns_oi_increases_unconfirmed(self):
        """
        Scenario 2: Price breaks level, returns back, OI increases -> Signal is UNCONFIRMED.
        OI rises from 1000.0 to 1050.0 (+5.0%). Positions were opened rather than liquidated.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=1050.0),  # Pierces 105, returns, but OI increased
            self.make_candle(3, 99.5, 100, 97, 98, oi=1052.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(fb["oiConfirmed"])
        self.assertEqual(fb["statusLabel"], "Непідтверджений хибний пробій")
        self.assertAlmostEqual(fb["oiDeltaPct"], 5.0, places=2)
        self.assertIn("Непідтверджений", fb["formation"])

    def test_scenario_3_breakout_returns_oi_flat_or_noise_unconfirmed(self):
        """
        Scenario 3: Price breaks level, returns back, OI barely changes (noise) -> Signal is UNCONFIRMED.
        OI changes from 1000.0 to 999.8 (-0.02%), within noise threshold (0.05%) and less than min drop (0.25%).
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=999.8),  # Negligible change within noise
            self.make_candle(3, 99.5, 100, 97, 98, oi=999.8),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(fb["oiConfirmed"])
        self.assertEqual(fb["statusLabel"], "Непідтверджений хибний пробій")
        self.assertEqual(fb["oiReason"], "OI_NOISE")

    def test_scenario_4a_oi_data_missing_unconfirmed(self):
        """
        Scenario 4a: Price breaks level, returns back, but OI data is missing -> Signal is UNCONFIRMED.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=None),
            self.make_candle(1, 100, 101, 99, 100, oi=None),
            self.make_candle(2, 100, 106, 99, 99.5, oi=None),
            self.make_candle(3, 99.5, 100, 97, 98, oi=None),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(fb["oiConfirmed"])
        self.assertIsNone(fb["oiDeltaPct"])
        self.assertEqual(fb["oiReason"], "MISSING_DATA")

    def test_scenario_4b_oi_data_stale_unconfirmed(self):
        """
        Scenario 4b: Price breaks level, returns back, but external tracker snapshot is stale -> Signal is UNCONFIRMED.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100),
            self.make_candle(1, 100, 101, 99, 100),
            self.make_candle(2, 100, 106, 99, 99.5),
            self.make_candle(3, 99.5, 100, 97, 98),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        
        # Tracker snapshots from 2000 seconds ago (far exceeding stale tolerance)
        old_time = candles[0]["time"] - 2000
        tracker = OITracker(coin="TEST")
        tracker.record_snapshot(oi=1000.0, price=100.0, timestamp=old_time)

        res = detect_false_breakouts(candles, levels, interval="5m", oi_tracker=tracker)
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(fb["oiConfirmed"])
        self.assertEqual(fb["oiReason"], "STALE_DATA")

    def test_scenario_5_oi_decreases_but_price_does_not_return_not_a_false_breakout(self):
        """
        Scenario 5: OI decreases, but price does NOT return across the level -> NOT a false breakout.
        No false breakout signal should be produced.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 106, 99, 106, oi=950.0),  # Pierces and closes above 105
            self.make_candle(2, 106, 110, 105.5, 109, oi=900.0),  # Continues pump
            self.make_candle(3, 109, 114, 108.5, 113, oi=850.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 0)

    def test_scenario_6_support_false_breakout_confirmed_with_oi_drop(self):
        """
        Scenario 6: Support level false breakout (Bullish Sweep) with OI drop -> CONFIRMED.
        OI drops from 2000.0 to 1940.0 (-3.0%).
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=2000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=2000.0),
            self.make_candle(2, 100, 101, 92, 96, oi=1940.0),  # Breaks 95 to 92, closes at 96 (> 95)
            self.make_candle(3, 96, 98, 95.5, 97, oi=1938.0),
        ]
        levels = [{"price": 95.0, "type": "support", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["type"], "bullish_sweep")
        self.assertEqual(fb["direction"], "LONG")
        self.assertEqual(fb["confirmationStatus"], "CONFIRMED")
        self.assertTrue(fb["oiConfirmed"])
        self.assertAlmostEqual(fb["oiDeltaPct"], -3.0, places=2)
        self.assertIn("Підтверджений хибний пробій підтримки", fb["formation"])

    def test_scenario_7_two_candle_breakout_confirmed_with_oi_drop(self):
        """
        Scenario 7: Two-candle false breakout with return confirmed by OI drop.
        Candle 2 closes above 105 (breakout). Candle 3 returns and closes below 105 (return).
        OI before breakout is 1000.0, OI on return is 970.0 (-3.0%).
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 101, 107, 101, 106, oi=995.0),  # Closes 106 > 105
            self.make_candle(3, 106, 106.5, 102, 103, oi=970.0), # Returns 103 < 105 with -3.0% OI
            self.make_candle(4, 103, 103.5, 98, 99, oi=965.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 3}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        self.assertEqual(fb["confirmationStatus"], "CONFIRMED")
        self.assertTrue(fb["oiConfirmed"])
        self.assertEqual(fb["subType"], "two_candle_reversal")
        self.assertAlmostEqual(fb["oiDeltaPct"], -3.0, places=2)

    def test_scenario_8_no_look_ahead_bias(self):
        """
        Scenario 8: Strictly no look-ahead bias.
        OI only drops on future candle 4 (+600s later), but was flat on candle 2 (confirmation).
        Signal at candle 2 MUST NOT look into candle 4 data.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=1000.0),  # Return at candle 2: OI unchanged (0.0%)
            self.make_candle(3, 99.5, 100, 97, 98, oi=1000.0),
            self.make_candle(4, 98, 98.5, 95, 96, oi=800.0),     # Future candle 4 has massive drop (-20%)
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]
        res = detect_false_breakouts(candles, levels, interval="5m")
        self.assertEqual(len(res), 1)
        fb = res[0]
        # At candle 2 confirmation time, delta is 0.0%, NOT -20.0%
        self.assertEqual(fb["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(fb["oiConfirmed"])
        self.assertAlmostEqual(fb["oiDeltaPct"], 0.0, places=2)

    def test_scenario_9_configurable_parameters(self):
        """
        Scenario 9: Verifies that min_oi_drop_pct and other config parameters are customizable.
        If min_oi_drop_pct is 1.0%, an OI drop of -0.5% is NOT confirmed.
        If min_oi_drop_pct is lowered to 0.3%, the same drop IS confirmed.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=995.0),  # Drop of -0.5%
            self.make_candle(3, 99.5, 100, 97, 98, oi=995.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]

        # With strict 1.0% threshold -> UNCONFIRMED
        res_strict = detect_false_breakouts(candles, levels, interval="5m", min_oi_drop_pct=1.0)
        self.assertEqual(res_strict[0]["confirmationStatus"], "UNCONFIRMED")
        self.assertFalse(res_strict[0]["oiConfirmed"])

        # With 0.3% threshold -> CONFIRMED
        res_relaxed = detect_false_breakouts(candles, levels, interval="5m", min_oi_drop_pct=0.3)
        self.assertEqual(res_relaxed[0]["confirmationStatus"], "CONFIRMED")
        self.assertTrue(res_relaxed[0]["oiConfirmed"])

    def test_scenario_10_only_confirmed_filter(self):
        """
        Scenario 10: only_confirmed=True filters out UNCONFIRMED signals.
        """
        candles = [
            self.make_candle(0, 100, 102, 98, 100, oi=1000.0),
            self.make_candle(1, 100, 101, 99, 100, oi=1000.0),
            self.make_candle(2, 100, 106, 99, 99.5, oi=1020.0),  # OI increases -> unconfirmed
            self.make_candle(3, 99.5, 100, 97, 98, oi=1020.0),
        ]
        levels = [{"price": 105.0, "type": "resistance", "touches": 2}]

        res_all = detect_false_breakouts(candles, levels, interval="5m", only_confirmed=False)
        self.assertEqual(len(res_all), 1)
        self.assertEqual(res_all[0]["confirmationStatus"], "UNCONFIRMED")

        res_confirmed_only = detect_false_breakouts(candles, levels, interval="5m", only_confirmed=True)
        self.assertEqual(len(res_confirmed_only), 0)


if __name__ == "__main__":
    unittest.main()

