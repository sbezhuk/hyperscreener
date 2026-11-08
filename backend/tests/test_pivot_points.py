import unittest
from datetime import datetime, timezone
from app.analyzer.levels import (
    calculate_pivot_points,
    extract_previous_period_ohlc,
    analyze_levels,
)


class TestPivotPoints(unittest.TestCase):
    """
    Unit tests for Classic Floor Pivot Points and enhanced Support/Resistance levels.
    """

    def test_pivot_point_exact_formulas(self):
        """
        Validates exact mathematical formula implementation:
          PP = (High + Low + Close) / 3
          R1 = 2 * PP - Low
          R2 = PP + (High - Low)
          R3 = High + 2 * (PP - Low)
          S1 = 2 * PP - High
          S2 = PP - (High - Low)
          S3 = Low - 2 * (High - PP)
        """
        high = 2000.0
        low = 1900.0
        close = 1950.0

        pivots = calculate_pivot_points(high=high, low=low, close=close)

        expected_pp = (2000.0 + 1900.0 + 1950.0) / 3.0  # 1950.0
        expected_r1 = (2.0 * expected_pp) - 1900.0       # 2000.0
        expected_r2 = expected_pp + (2000.0 - 1900.0)    # 2050.0
        expected_r3 = 2000.0 + 2.0 * (expected_pp - 1900.0)  # 2100.0
        expected_s1 = (2.0 * expected_pp) - 2000.0       # 1900.0
        expected_s2 = expected_pp - (2000.0 - 1900.0)    # 1850.0
        expected_s3 = 1900.0 - 2.0 * (2000.0 - expected_pp)  # 1800.0

        self.assertEqual(pivots["pp"], expected_pp)
        self.assertEqual(pivots["r1"], expected_r1)
        self.assertEqual(pivots["r2"], expected_r2)
        self.assertEqual(pivots["r3"], expected_r3)
        self.assertEqual(pivots["s1"], expected_s1)
        self.assertEqual(pivots["s2"], expected_s2)
        self.assertEqual(pivots["s3"], expected_s3)

    def test_pivot_point_asymmetric_values(self):
        """
        Validates with asymmetric non-centered values:
          High = 100.0, Low = 80.0, Close = 96.0
        """
        high = 100.0
        low = 80.0
        close = 96.0

        pivots = calculate_pivot_points(high=high, low=low, close=close)

        expected_pp = round((100.0 + 80.0 + 96.0) / 3.0, 2)  # 92.0
        expected_r1 = round((2.0 * 92.0) - 80.0, 2)          # 104.0
        expected_r2 = round(92.0 + (100.0 - 80.0), 2)         # 112.0
        expected_r3 = round(100.0 + 2.0 * (92.0 - 80.0), 2)  # 124.0
        expected_s1 = round((2.0 * 92.0) - 100.0, 2)         # 84.0
        expected_s2 = round(92.0 - (100.0 - 80.0), 2)         # 72.0
        expected_s3 = round(80.0 - 2.0 * (100.0 - 92.0), 2)  # 64.0

        self.assertEqual(pivots["pp"], expected_pp)
        self.assertEqual(pivots["r1"], expected_r1)
        self.assertEqual(pivots["r2"], expected_r2)
        self.assertEqual(pivots["r3"], expected_r3)
        self.assertEqual(pivots["s1"], expected_s1)
        self.assertEqual(pivots["s2"], expected_s2)
        self.assertEqual(pivots["s3"], expected_s3)
        # Ensure monotonic order: S3 < S2 < S1 < PP < R1 < R2 < R3
        self.assertLess(pivots["s3"], pivots["s2"])
        self.assertLess(pivots["s2"], pivots["s1"])
        self.assertLess(pivots["s1"], pivots["pp"])
        self.assertLess(pivots["pp"], pivots["r1"])
        self.assertLess(pivots["r1"], pivots["r2"])
        self.assertLess(pivots["r2"], pivots["r3"])

    def test_extract_previous_period_ohlc_multi_day(self):
        """
        Validates extraction of previous completed day from candles spanning multiple UTC calendar days.
        """
        # Day 1: 2026-01-01 (1767225600)
        # Day 2: 2026-01-02 (1767312000) -> completed previous day
        # Day 3: 2026-01-03 (1767398400) -> current forming day
        t1 = 1767225600
        t2 = 1767312000
        t3 = 1767398400

        candles = [
            # Day 1
            {"time": t1 + 3600, "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 10.0},
            # Day 2 (Target: High=115, Low=95, Close=110, Open=103)
            {"time": t2 + 3600, "open": 103.0, "high": 115.0, "low": 101.0, "close": 108.0, "volume": 20.0},
            {"time": t2 + 7200, "open": 108.0, "high": 112.0, "low": 95.0, "close": 110.0, "volume": 30.0},
            # Day 3 (Current)
            {"time": t3 + 3600, "open": 110.0, "high": 114.0, "low": 109.0, "close": 112.0, "volume": 15.0},
        ]

        extracted = extract_previous_period_ohlc(candles, interval="1h", period_type="daily")
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["high"], 115.0)
        self.assertEqual(extracted["low"], 95.0)
        self.assertEqual(extracted["close"], 110.0)
        self.assertEqual(extracted["open"], 103.0)
        self.assertEqual(extracted["period"], "daily")

    def test_extract_previous_period_ohlc_weekly(self):
        """
        Validates weekly period extraction on 1d timeframe.
        """
        # 14 daily candles spanning 2 weeks
        # Jan 5 2026 was Monday (1767571200)
        start_ts = 1767571200
        candles = []
        for i in range(14):
            candles.append({
                "time": start_ts + i * 86400,
                "open": 200.0 + i,
                "high": 210.0 + i,
                "low": 190.0 + i,
                "close": 205.0 + i,
                "volume": 100.0,
            })

        extracted = extract_previous_period_ohlc(candles, interval="1d", period_type="weekly")
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["period"], "weekly")
        self.assertIn("-W", extracted["period_key"])

    def test_analyze_levels_integration_contains_pivots(self):
        """
        Validates that analyze_levels includes pivot_points in output,
        and that resistances and supports contain pivot points (is_pivot=True).
        """
        candles = [
            {"time": 1700000000 + i * 3600, "open": 100.0 + (i % 5), "high": 105.0 + (i % 5), "low": 95.0, "close": 101.0, "volume": 100.0}
            for i in range(50)
        ]

        result = analyze_levels(candles, interval="1h", include_pivots=True)

        self.assertIn("pivot_points", result)
        self.assertIn("pp", result["pivot_points"])
        self.assertIn("r1", result["pivot_points"])
        self.assertIn("s1", result["pivot_points"])

        all_levels = result["resistances"] + result["supports"]
        pivot_levels = [lvl for lvl in all_levels if lvl.get("is_pivot")]
        self.assertGreater(len(pivot_levels), 0)

        # Check required fields on each level
        for lvl in all_levels:
            self.assertIn("price", lvl)
            self.assertIn("distPct", lvl)
            self.assertIn("touches", lvl)
            self.assertIn("firstTime", lvl)
            self.assertIn("latestTime", lvl)
            self.assertGreater(lvl["firstTime"], 0)
            self.assertGreater(lvl["latestTime"], 0)

    def test_role_reversal_status(self):
        """
        When price trades above R1, R1 acts as support with status='retested'.
        When price trades below S1, S1 acts as resistance with status='retested'.
        """
        high = 100.0
        low = 90.0
        close = 95.0
        # PP = 95, R1 = 100, S1 = 90
        candles = [
            {"time": 1000 + i * 60, "open": 105.0, "high": 108.0, "low": 104.0, "close": 106.0, "volume": 50.0}
            for i in range(20)
        ]
        # Current price = 106.0 (which is ABOVE R1=100.0)
        result = analyze_levels(candles, interval="5m", prev_high=high, prev_low=low, prev_close=close, include_pivots=True)

        # R1 should now be classified under supports as a flipped level with status='retested'
        sup_r1 = next((s for s in result["supports"] if s.get("pivot_label") == "R1"), None)
        self.assertIsNotNone(sup_r1)
        self.assertEqual(sup_r1["status"], "retested")


if __name__ == "__main__":
    unittest.main()
